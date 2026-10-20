// Included inside dmxeval.cpp's private namespace. A graph owns only evaluation
// state; the authored document remains immutable across clips and compiles.
bool rigClass(const std::string& c) {
    return c=="DmeRigPointConstraintOperator"||c=="DmeRigOrientConstraintOperator"||
        c=="DmeRigAimConstraintOperator"||c=="DmeRigParentConstraintOperator"||
        c=="DmeRigRotationConstraintOperator"||c=="DmeRigIKConstraintOperator"||
        c=="DmeRigTwistConstraintOperator";
}
bool supported(const std::string& c) {
    if(rigClass(c)||c=="DmeConnectionOperator"||c=="DmeExpressionOperator"||c=="DmeTransformOperator")return true;
    for(const char* type:{"Vector2","Vector3","Vector4","Quaternion","QAngle","VMatrix","Color"})
        if(c==std::string("DmePack")+type+"Operator"||c==std::string("DmeUnpack")+type+"Operator")return true;
    return false;
}
pm::Vector3 add(pm::Vector3 a,pm::Vector3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
pm::Vector3 sub(pm::Vector3 a,pm::Vector3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
pm::Vector3 mul(pm::Vector3 a,float s){return {a.x*s,a.y*s,a.z*s};}
float dot(pm::Vector3 a,pm::Vector3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
pm::Vector3 cross(pm::Vector3 a,pm::Vector3 b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
pm::Vector3 unit(pm::Vector3 a,const char* what){const float n=dot(a,a);if(!std::isfinite(n)||n<1e-14f)throw EvalError(std::string("degenerate ")+what);return mul(a,1/std::sqrt(n));}
pm::Quaternion normalized(pm::Quaternion q){const float n=q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w;if(!std::isfinite(n)||n<1e-12f)throw EvalError("invalid rig quaternion");pm::QuaternionNormalize(q);return q;}
pm::Quaternion qmul(pm::Quaternion a,pm::Quaternion b){pm::Quaternion q;pm::QuaternionMult(a,b,q);return normalized(q);}
pm::Quaternion inv(pm::Quaternion q){q=normalized(q);return {-q.x,-q.y,-q.z,q.w};}
pm::Quaternion orient(const pm::matrix3x4& m){pm::Quaternion q;pm::Vector3 p;pm::MatrixAngles(m,q,p);return normalized(q);}
pm::Vector3 pos(const pm::matrix3x4& m){return {m.m[0][3],m.m[1][3],m.m[2][3]};}
V vectorValue(pm::Vector3 p){return {Kind::V3,{p.x,p.y,p.z}};}
V quaternionValue(pm::Quaternion q){q=normalized(q);return {Kind::Quat,{q.x,q.y,q.z,q.w}};}
pm::Quaternion slerp(pm::Quaternion a,pm::Quaternion b,float f){pm::Quaternion q;pm::QuaternionSlerp(a,b,f,q);return normalized(q);}
pm::Quaternion axisAngle(pm::Vector3 axis,float radians){axis=unit(axis,"rotation axis");const float s=std::sin(radians/2);return {axis.x*s,axis.y*s,axis.z*s,std::cos(radians/2)};}
pm::Quaternion aimOrientation(pm::Vector3 forward,pm::Vector3 up,bool ik) {
    forward=unit(forward,"aim direction");up=unit(sub(up,mul(forward,dot(forward,up))),"aim up vector");
    const auto side=unit(ik?cross(up,forward):cross(forward,up),"aim side vector");
    pm::matrix3x4 m;const auto x=ik?forward:side,y=ik?side:forward;
    for(int i=0;i<3;++i){m.m[i][0]=(&x.x)[i];m.m[i][1]=(&y.x)[i];m.m[i][2]=(&up.x)[i];}
    return orient(m);
}
struct ClipPath {const E* clip=nullptr;std::vector<const E*> path;};
struct Node {const E* e;std::vector<Key> in,out;Log log;bool channel=false;std::vector<const E*> path;};
class Graph {
    std::vector<Node> nodes;
    std::map<Key,std::vector<int>> writers;
    std::map<Key,V> cache,inputs;
    std::map<const E*,const E*> parents;
    std::vector<int> state;
    std::set<int> active,roots;
    std::set<const E*> worldStack;
    int now=0;
    void addNode(Node n){int i=int(nodes.size());for(const auto& k:n.out)writers[k].push_back(i);nodes.push_back(std::move(n));}
    const E* transform(const E* dag)const {const E* t=dag?dag->GetElement("transform"):nullptr;if(!t)throw EvalError("rig DAG has no transform");return t;}
    const E* target(const E* holder)const {const E* d=holder?holder->GetElement("target"):nullptr;if(!d)throw EvalError("missing rig target");transform(d);return d;}
    V get(const E* e,const char* attr,V fallback,int index=0){if(!e)throw EvalError("missing rig element");Key k=key(e,attr,index);if(!e->Get(attr)&&!writers.count(k))return fallback;return read(k);}
    float number(const Key& k){V v=read(k);if(width(v.kind)!=1)throw EvalError("expected scalar input");finite(v);return v.v[0];}
    float number(const E* e,const char* attr,float fallback=0,int index=0){V v=get(e,attr,scalar(fallback),index);if(width(v.kind)!=1)throw EvalError("expected scalar rig parameter");finite(v);return v.v[0];}
    pm::Vector3 vector(const E* e,const char* attr,pm::Vector3 fallback={},int index=0){V v=get(e,attr,vectorValue(fallback),index);if(v.kind!=Kind::V3)throw EvalError("expected Vector3 rig parameter");finite(v);return {v.v[0],v.v[1],v.v[2]};}
    pm::Quaternion quaternion(const E* e,const char* attr){V v=get(e,attr,{Kind::Quat,{0,0,0,1}});if(v.kind!=Kind::Quat)throw EvalError("expected Quaternion rig parameter");return normalized({v.v[0],v.v[1],v.v[2],v.v[3]});}
    pm::matrix3x4 parentWorld(const E* dag){auto it=parents.find(dag);return it==parents.end()||!it->second?pm::matrix3x4{}:world(it->second);}
    pm::matrix3x4 world(const E* dag) {
        if(!worldStack.insert(dag).second)throw EvalError("cyclic rig DAG dependency at '"+dag->name+"'");
        const E* t=transform(dag);auto p=parentWorld(dag);
        auto m=pm::ConcatTransforms(p,pm::QuaternionMatrix(quaternion(t,"orientation"),vector(t,"position")));
        worldStack.erase(dag);return m;
    }
    void outputPosition(const E* dag,pm::Vector3 p){put(key(transform(dag),"position"),vectorValue(p));}
    void outputOrientation(const E* dag,pm::Quaternion q){put(key(transform(dag),"orientation"),quaternionValue(q));}
    void put(const Key& k,V v) {
        finite(v);int count=0;for(int i:writers[k])if(active.count(i))++count;
        if(count>1)throw EvalError("multiple animation writers for '"+k.e->name+"."+k.attr+"'");
        if(k.e->className.find("Operator")!=std::string::npos&&!supported(k.e->className))throw EvalError("unsupported connected operator "+k.e->className);
        if(const auto* a=k.e->Get(k.attr)) {
            const V expected=value(a,k.index);
            if(expected.kind!=v.kind) {
                if(width(expected.kind)==1&&width(v.kind)==1){v.kind=expected.kind;if(v.kind==Kind::Bool)v.v[0]=v.v[0]!=0;if(v.kind==Kind::Int)v.v[0]=std::trunc(v.v[0]);}
                else throw EvalError("animation type mismatch for '"+k.attr+"'");
            }
        }
        cache[k]=std::move(v);
    }
    std::pair<pm::Vector3,float> targetPosition(const E* e,bool parent=false) {
        const auto* ts=e->GetElementArray("targets");if(!ts||ts->empty())throw EvalError("rig constraint has no targets");
        pm::Vector3 p{};float total=0;
        for(const E* t:*ts){const float w=number(t,"targetWeight");if(w<0)throw EvalError("negative rig target weight");const auto m=world(target(t));const auto offset=vector(t,"vecOffset");p=add(p,mul(parent?pm::VectorTransform(offset,m):add(pos(m),offset),w));total+=w;}
        if(!std::isfinite(total))throw EvalError("non-finite rig target weight sum");
        return {total>0?mul(p,1/total):pm::Vector3{},std::min(total,1.0f)};
    }
    pm::Quaternion targetOrientation(const E* e) {
        const auto* ts=e->GetElementArray("targets");if(!ts||ts->empty())throw EvalError("rig constraint has no targets");
        std::vector<pm::Quaternion> qs;std::vector<float> ws;float total=0;
        for(const E* t:*ts){float w=number(t,"targetWeight");if(w<0)throw EvalError("negative rig target weight");qs.push_back(qmul(orient(world(target(t))),quaternion(t,"oOffset")));ws.push_back(w);total+=w;}
        if(total<=0)return {0,0,0,1};if(!std::isfinite(total))throw EvalError("non-finite rig target weight sum");if(qs.size()==1)return qs.front();
        pm::Vector3 sum{};
        for(size_t i=0;i<qs.size();++i){pm::Quaternion q;pm::QuaternionAlign(qs[0],qs[i],q);float r=std::sqrt(q.x*q.x+q.y*q.y+q.z*q.z);float s=(r>1e-5f?std::atan2(r,q.w)/r:0)*ws[i]/total;sum=add(sum,{q.x*s,q.y*s,q.z*s});}
        float r=std::sqrt(dot(sum,sum)),s=r>=1e-5f?std::sin(r)/r:0;return normalized({sum.x*s,sum.y*s,sum.z*s,std::cos(r)});
    }
    void solveRig(const Node& n) {
        const E* e=n.e;const auto& c=e->className;
        if(number(e,"mode")!=0)throw EvalError("reverse rig mode is not supported");
        if(c=="DmeRigRotationConstraintOperator") {
            const E* dag=target(e->GetElement("slave"));const auto* axes=e->GetVector3Array("axies");const auto* rotations=e->GetFloatArray("rotations");
            if(!axes||!rotations||axes->size()!=rotations->size())throw EvalError("Rotation requires equal axies and rotations arrays");
            pm::Quaternion q{0,0,0,1};for(size_t j=0;j<axes->size();++j)q=qmul(axisAngle(vector(e,"axies",{},int(j)),number(e,"rotations",0,int(j))*float(3.14159265358979323846/180)),q);
            outputOrientation(dag,q);return;
        }
        if(c=="DmeRigIKConstraintOperator") {
            const E* start=e->GetElement("startJoint"),*mid=e->GetElement("midJoint"),*end=e->GetElement("endJoint");
            const E* a=target(start),*b=target(mid),*d=target(end);
            if(parents[b]!=a||parents[d]!=b)throw EvalError("IK joints must form a two-bone chain");
            const auto parent=parentWorld(a);auto targetAndWeight=targetPosition(e);const float weight=targetAndWeight.second;
            auto qa=quaternion(start,"orientation"),qb=quaternion(mid,"orientation");
            if(weight>0) {
                const auto origin=vector(transform(a),"position"),axis=sub(pm::VectorITransform(targetAndWeight.first,parent),origin);
                const auto forward=unit(axis,"IK target direction");
                const auto bp=vector(transform(b),"position"),ep=vector(transform(d),"position");
                const float la=std::sqrt(dot(bp,bp)),lb=std::sqrt(dot(ep,ep));if(!std::isfinite(la+lb)||la<1e-7f||lb<1e-7f)throw EvalError("IK has a zero-length bone");
                const float length=std::clamp(std::sqrt(dot(axis,axis)),std::max(std::fabs(la-lb),1e-7f),la+lb);
                const E* pv=e->GetElement("pvTarget");const auto pole=pv?sub(pm::VectorITransform(pos(world(pv)),parent),origin):pm::VectorIRotate(vector(e,"poleVector",{0,0,1}),parent);
                const auto up=unit(sub(pole,mul(forward,dot(forward,pole))),"IK pole vector");
                const float along=(la*la-lb*lb+length*length)/(2*length),height=std::sqrt(std::max(0.0f,la*la-along*along));
                const auto middle=add(mul(forward,along),mul(up,height)),last=sub(mul(forward,length),middle);
                const auto solvedA=qmul(aimOrientation(middle,up,true),quaternion(e,"startOffset"));
                const auto solvedB=qmul(qmul(inv(solvedA),aimOrientation(last,up,true)),quaternion(e,"midOffset"));
                qa=slerp(qa,solvedA,weight);qb=slerp(qb,solvedB,weight);
            }
            outputOrientation(a,qa);outputOrientation(b,qb);return;
        }
        if(c=="DmeRigTwistConstraintOperator") {
            const auto* ts=e->GetElementArray("targets"),*slaves=e->GetElementArray("twistJoints");if(!ts||ts->size()!=2||!slaves||slaves->empty())throw EvalError("Twist requires two targets and slaves");
            const E* a=target((*ts)[0]),*b=target((*ts)[1]);
            const auto parent=world(a),childWorld=world(b);
            auto child=pm::ConcatTransforms(pm::MatrixInvert(parent),childWorld);
            // Subtract positions before rotating. Multiplying two full affine
            // transforms subtracts rounded, rotated world positions instead,
            // turning coincident joints into a small arbitrary twist axis.
            const auto displacement=pm::VectorIRotate(sub(pos(childWorld),pos(parent)),parent);
            child.m[0][3]=displacement.x;child.m[1][3]=displacement.y;child.m[2][3]=displacement.z;
            const bool inverse=number(e,"inverse")!=0;const auto base=quaternion(e,inverse?"parentBindRotation":"childBindRotation");
            const auto localParent=pm::ConcatTransforms(pm::MatrixInvert(parentWorld(a)),parent);
            const auto relative=qmul(inv(base),inverse?orient(localParent):orient(child));
            const auto up=unit(vector(e,"upVector",{0,1,0}),"Twist up vector");
            for(const E* slave:*slaves) {
                const E* dag=target(slave);auto q=quaternion(slave,"orientation");auto axis=pos(child);
                const float epsilon=std::numeric_limits<float>::epsilon()*10;
                if(dot(axis,axis)>=epsilon*epsilon) {
                    axis=unit(axis,"Twist axis");const auto ra=pm::VectorRotate(axis,pm::QuaternionMatrix(inverse?relative:inv(base),{})),ru=pm::VectorRotate(up,pm::QuaternionMatrix(relative,{}));
                    if(1-std::fabs(dot(ra,up))>=epsilon&&1-std::fabs(dot(ra,ru))>=epsilon) {
                        const auto u=unit(sub(up,mul(ra,dot(up,ra))),"Twist projection"),v=unit(sub(ru,mul(ra,dot(ru,ra))),"Twist projection");
                        if(std::fabs(u.x-v.x)>.001f||std::fabs(u.y-v.y)>.001f||std::fabs(u.z-v.z)>.001f) {
                            const float angle=std::acos(std::clamp(dot(u,v),-1.0f,1.0f))*(dot(cross(u,v),ra)<0?-1:1);
                            pm::Quaternion portion;pm::QuaternionScale(axisAngle(axis,angle),number(slave,"weight")-(inverse?1:0),portion);q=qmul(portion,q);
                        }
                    }
                }
                // Twist slave positions are authored local offsets under the
                // parent target, even when the actual DAG parent differs.
                const auto t=transform(dag);const auto input=inputs.find(key(t,"position"));
                const auto authored=dag->GetElement("transform")->GetVector3("position");
                const auto desired=pm::ConcatTransforms(parent,pm::QuaternionMatrix(q,{authored.x,authored.y,authored.z}));
                const auto local=pm::ConcatTransforms(pm::MatrixInvert(parentWorld(dag)),desired);
                outputPosition(dag,pos(local));outputOrientation(dag,orient(local));
            }
            return;
        }
        const E* slave=e->GetElement("slave"),*dag=target(slave);const auto parent=parentWorld(dag);
        const auto base=pm::ConcatTransforms(parent,pm::QuaternionMatrix(quaternion(slave,"orientation"),vector(slave,"position")));
        const auto targetAndWeight=targetPosition(e,c=="DmeRigParentConstraintOperator");const auto p=targetAndWeight.first;const float weight=targetAndWeight.second;
        if(c=="DmeRigPointConstraintOperator"||c=="DmeRigParentConstraintOperator")outputPosition(dag,pm::VectorITransform(add(mul(pos(base),1-weight),mul(p,weight)),parent));
        if(c=="DmeRigOrientConstraintOperator"||c=="DmeRigParentConstraintOperator")outputOrientation(dag,qmul(inv(orient(parent)),slerp(orient(base),targetOrientation(e),weight)));
        if(c=="DmeRigAimConstraintOperator") {
            auto q=quaternion(slave,"orientation");
            if(weight>0) {
                auto up=vector(e,"upVector",{0,0,1});const int type=int(number(e,"upType"));const E* space=e->GetElement("upSpaceTarget");
                if(type<0||type>3)throw EvalError("invalid aim up type");
                const auto slavePosition=vector(transform(dag),"position");
                if(type==2&&space)up=sub(pos(world(space)),pm::VectorTransform(slavePosition,parent));else if(type==0&&space)up=pm::VectorRotate(up,world(space));else if(type==3)up=pm::VectorRotate(up,parent);
                const auto forward=sub(pm::VectorITransform(p,parent),slavePosition);
                q=slerp(q,qmul(aimOrientation(forward,pm::VectorIRotate(up,parent),false),quaternion(e,"aimOffset")),weight);
            }
            outputOrientation(dag,q);
        }
    }
    int channelTime(const Node& n,bool& enabled,bool* ending=nullptr,bool* starting=nullptr)const {
        double t=now;enabled=true;
        for(size_t i=0;i<n.path.size();++i){const E* tf=n.path[i]->GetElement("timeFrame");const int start=timeField(tf,"start"),duration=timeField(tf,"duration");const float scale=tf?tf->GetFloat("scale",1):1;
            if(!std::isfinite(scale)||scale==0||duration<0)throw EvalError("invalid clip time scale or duration");
            if(i>0&&(t<start||t>double(start)+duration)){enabled=false;return 0;}
            if(i>0&&duration>0){if(ending&&t==double(start)+duration)*ending=true;if(starting&&t==start)*starting=true;}
            t=(t-start)*scale+timeField(tf,"offset");if(!std::isfinite(t)||t<std::numeric_limits<int>::min()||t>std::numeric_limits<int>::max())throw EvalError("scaled clip time out of range");t=std::floor(t+.5);
        }
        return int(t);
    }
    void evaluate(int i) {
        if(state[i]==2)return;if(state[i]==1)throw EvalError("cyclic animation dependency at '"+nodes[i].e->name+"'");state[i]=1;
        const Node& n=nodes[i];const auto& c=n.e->className;
        if(n.channel){bool enabled;const int t=channelTime(n,enabled);if(enabled)put(n.out[0],n.log.e&&(n.log.hasKeys()||n.log.hasDefault()||n.in.empty())?n.log.sample(t):read(n.in[0]));}
        else if(rigClass(c))solveRig(n);
        else if(c=="DmeConnectionOperator"){V v=read(n.in[0]);for(const auto& k:n.out)put(k,v);}
        else if(c=="DmeExpressionOperator") {
            V expr=get(n.e,"expr",{Kind::String,{},""});if(expr.kind!=Kind::String)throw EvalError("expression operator has invalid expr");
            auto lookup=[&](const std::string& name){return number(key(n.e,name));};put(n.out[0],scalar(Expression(expr.text,lookup).evaluate()));
        }else if(c=="DmeTransformOperator") {
            V p{Kind::V3,{}},q{Kind::Quat,{}};for(int j=0;j<3;++j)p.v[j]=number(n.in[j]);for(int j=0;j<4;++j)q.v[j]=number(n.in[j+3]);put(n.out[0],p);put(n.out[1],q);
        }else if(c.find("DmePack")==0) {
            V v;v.kind=c.find("Quaternion")!=std::string::npos?Kind::Quat:c.find("Vector2")!=std::string::npos?Kind::V2:c.find("Vector3")!=std::string::npos?Kind::V3:c.find("QAngle")!=std::string::npos?Kind::QAngle:c.find("VMatrix")!=std::string::npos?Kind::Matrix:c.find("Color")!=std::string::npos?Kind::Color:Kind::V4;
            for(size_t j=0;j<n.in.size();++j){v.v[j]=number(n.in[j]);if(v.kind==Kind::Color)v.v[j]=std::trunc(std::clamp(v.v[j]*255.999f,0.0f,255.0f));}put(n.out[0],v);
        }else {V v=read(n.in[0]);if(width(v.kind)!=int(n.out.size()))throw EvalError("unpack input width mismatch");for(size_t j=0;j<n.out.size();++j)put(n.out[j],scalar(v.v[j]*(v.kind==Kind::Color?1/255.999f:1)));}
        state[i]=2;
    }
    void rigOutputs(Node& n) {
        auto append=[&](const E* dag,bool p,bool q){if(p)n.out.push_back(key(transform(dag),"position"));if(q)n.out.push_back(key(transform(dag),"orientation"));};
        const auto& c=n.e->className;
        if(c=="DmeRigIKConstraintOperator"){append(target(n.e->GetElement("startJoint")),false,true);append(target(n.e->GetElement("midJoint")),false,true);target(n.e->GetElement("endJoint"));}
        else if(c=="DmeRigTwistConstraintOperator"){const auto* slaves=n.e->GetElementArray("twistJoints");if(!slaves||slaves->empty())throw EvalError("Twist has no slaves");for(const E* s:*slaves)append(target(s),true,true);}
        else append(target(n.e->GetElement("slave")),c=="DmeRigPointConstraintOperator"||c=="DmeRigParentConstraintOperator",c!="DmeRigPointConstraintOperator");
        // Track numeric parameter/target edges for activation. Solver reads
        // only the channels it actually consumes, so slave output references
        // here do not create a false feedback edge.
        std::set<const E*> visited;
        auto gather=[&](auto&& self,const E* e)->void{if(!e||!visited.insert(e).second)return;for(const auto& a:e->attributes){if(auto p=std::get_if<dmx::ElementPtr>(&a.value))self(self,*p);else if(auto p=std::get_if<std::vector<dmx::ElementPtr>>(&a.value)){for(const E* t:*p)self(self,t);}else if(a.type!=dmx::AttrType::String&&a.type!=dmx::AttrType::Binary){if(dmx::IsArrayType(a.type)){for(size_t j=0;j<arraySize(&a);++j)n.in.push_back(key(e,a.name,int(j)));}else n.in.push_back(key(e,a.name));}}};
        gather(gather,n.e);
    }
public:
    Graph(const dmx::Datamodel& dm,const std::vector<ClipPath>& clips) {
        const E* skeleton=dm.root?dm.root->GetElement("skeleton"):nullptr;if(!skeleton&&dm.root)skeleton=dm.root->GetElement("model");
        for(const auto& ptr:dm.elements)if(const auto* children=ptr->GetElementArray("children"))for(const E* child:*children)if(child&&child->GetElement("transform")) {
            const E* parent=ptr.get()==skeleton?nullptr:ptr->GetElement("transform")?ptr.get():nullptr;
            auto old=parents.find(child);if(old!=parents.end()&&old->second!=parent)throw EvalError("DAG has multiple parents");parents[child]=parent;
        }
        for(const auto& cp:clips)if(const auto* channels=cp.clip->GetElementArray("channels"))for(const E* c:*channels) {
            if(!c||!c->GetString("toAttribute"))throw EvalError("invalid animation channel");Node n{c};n.channel=true;n.path=cp.path;n.out.push_back(key(c->GetElement("toElement"),*c->GetString("toAttribute"),c->GetInt("toIndex",0)));n.log=Log(c->GetElement("log"));
            if(!n.log.e||(!n.log.hasKeys()&&!n.log.hasDefault())){const auto* a=c->GetString("fromAttribute");if(a)n.in.push_back(key(c->GetElement("fromElement"),*a,c->GetInt("fromIndex",0)));else if(!n.log.e)throw EvalError("channel has neither a log nor a source");}
            roots.insert(int(nodes.size()));addNode(std::move(n));
        }
        std::set<const E*> rootRigs;if(dm.root)if(const auto* rs=dm.root->GetElementArray("constraints"))for(const E* e:*rs)rootRigs.insert(e);
        for(const auto& ptr:dm.elements){const E* e=ptr.get();const auto& c=e->className;if(!supported(c))continue;Node n{e};
            if(rigClass(c)){rigOutputs(n);if(rootRigs.count(e))roots.insert(int(nodes.size()));}
            else if(c=="DmeConnectionOperator"){n.in.push_back(reference(e->GetElement("input")));if(const auto* os=e->GetElementArray("outputs"))for(const E* o:*os)n.out.push_back(reference(o));}
            else if(c=="DmeExpressionOperator"){for(const auto& a:e->attributes)if((a.type==dmx::AttrType::Float&&a.name!="result")||a.name=="expr")n.in.push_back(key(e,a.name));n.out.push_back(key(e,"result"));}
            else if(c=="DmeTransformOperator"){for(const char* a:{"positionX","positionY","positionZ","orientationX","orientationY","orientationZ","orientationW"})n.in.push_back(key(e,a));const E* t=e->GetElement("transform");if(!t)throw EvalError("transform operator has no transform");n.out={key(t,"position"),key(t,"orientation")};}
            else {const bool pack=c.find("DmePack")==0,quat=c.find("Quaternion")!=std::string::npos,color=c.find("Color")!=std::string::npos,matrix=c.find("VMatrix")!=std::string::npos,angle=c.find("QAngle")!=std::string::npos;const int count=matrix?16:quat||color||c.find("Vector4")!=std::string::npos?4:c.find("Vector2")!=std::string::npos?2:3;
                std::vector<Key> scalars;const char* colors[]={"red","green","blue","alpha"};for(int j=0;j<count;++j)scalars.push_back(key(e,matrix?"m"+std::to_string(j/4)+std::to_string(j%4):color?colors[j]:std::string(1,"xyzw"[j])));
                Key combined=key(e,quat?"quaternion":color?"color":matrix?"vmatrix":angle?"qangle":"vector");if(pack){n.in=scalars;n.out={combined};}else{n.in={combined};n.out=scalars;}}
            addNode(std::move(n));
        }
        state.resize(nodes.size());
    }
    void frame(int t,const std::map<std::string,pm::matrix3x4>* external=nullptr) {
        now=t;cache.clear();inputs.clear();worldStack.clear();active.clear();std::fill(state.begin(),state.end(),0);
        if(external)for(const auto& item:parents){const E* dag=item.first;auto found=external->find(dag->name);if(found==external->end())continue;auto local=found->second;if(item.second){auto p=external->find(item.second->name);if(p==external->end())throw EvalError("missing authored rig parent '"+item.second->name+"'");local=pm::ConcatTransforms(pm::MatrixInvert(p->second),local);}inputs[key(transform(dag),"position")]=vectorValue(pos(local));inputs[key(transform(dag),"orientation")]=quaternionValue(orient(local));}
        for(int i:roots){bool enabled=true;if(nodes[i].channel)channelTime(nodes[i],enabled);if(enabled)active.insert(i);}
        // Adjacent clips may share a sample at their boundary. The incoming
        // clip owns that sample; actual interval overlaps still fail below.
        for(const auto& item:writers){bool incoming=false;for(int i:item.second)if(active.count(i)&&nodes[i].channel){bool enabled,ending=false,starting=false;channelTime(nodes[i],enabled,&ending,&starting);incoming|=starting&&!ending;}
            if(incoming)for(int i:item.second)if(active.count(i)&&nodes[i].channel){bool enabled,ending=false,starting=false;channelTime(nodes[i],enabled,&ending,&starting);if(ending&&!starting)active.erase(i);}}
        bool changed=true;while(changed){changed=false;for(size_t i=0;i<nodes.size();++i)if(!nodes[i].channel&&!active.count(int(i)))for(const auto& k:nodes[i].in){auto it=writers.find(k);if(it!=writers.end()&&std::any_of(it->second.begin(),it->second.end(),[&](int n){return active.count(n)!=0;})){active.insert(int(i));changed=true;break;}}}
        for(int i:active)evaluate(i);
    }
    V read(const Key& k,bool dependency=true) {
        auto found=cache.find(k);if(found!=cache.end())return found->second;auto w=writers.find(k);
        if(w!=writers.end()){int selected=-1;for(int i:w->second)if(active.count(i)){if(selected>=0)throw EvalError("multiple active animation writers");selected=i;}
            if(selected<0&&dependency){for(int i:w->second)if(!nodes[i].channel){if(selected>=0)throw EvalError("ambiguous animation dependency writer");selected=i;}if(selected>=0)active.insert(selected);}
            if(selected>=0){evaluate(selected);auto got=cache.find(k);if(got==cache.end())throw EvalError("operator did not produce its declared output");return got->second;}}
        if(auto p=inputs.find(k);p!=inputs.end())return p->second;
        if(k.e->className.find("Operator")!=std::string::npos&&!supported(k.e->className))throw EvalError("unsupported dependency operator "+k.e->className+" '"+k.e->name+"'");
        if(const auto* a=k.e->Get(k.attr))return value(a,k.index);
        if(supported(k.e->className)&&!rigClass(k.e->className)&&k.e->className!="DmeExpressionOperator")return scalar(0);
        if(k.attr=="position"||k.attr=="valuePosition")return {Kind::V3,{}};if(k.attr=="orientation"||k.attr=="valueOrientation")return {Kind::Quat,{0,0,0,1}};
        throw EvalError("missing dependency attribute '"+k.e->name+"."+k.attr+"'");
    }
    std::map<std::string,pm::matrix3x4> rigWorlds() {std::map<std::string,pm::matrix3x4> result;for(int i:active)if(rigClass(nodes[i].e->className))for(const auto& k:nodes[i].out)for(const auto& p:parents)if(p.first->GetElement("transform")==k.e)result[p.first->name]=world(p.first);return result;}
    std::vector<std::string> rigIds()const {std::vector<std::string> result;for(int i:active)if(rigClass(nodes[i].e->className))result.push_back(dmx::GuidToString(nodes[i].e->id));return result;}
    void checkUnsupported(const dmx::Datamodel& dm)const {
        std::set<const E*> changed;for(int i:active)for(const auto& k:nodes[i].out)changed.insert(k.e);
        for(const auto& ptr:dm.elements)if(ptr->className.find("Operator")!=std::string::npos&&!supported(ptr->className)){
            std::set<const E*> visited;auto connected=[&](auto&& self,const E* e)->bool{if(!e||!visited.insert(e).second)return false;if(changed.count(e))return true;for(const auto& a:e->attributes){if(const auto* p=std::get_if<dmx::ElementPtr>(&a.value)){if(self(self,*p))return true;}if(const auto* p=std::get_if<std::vector<dmx::ElementPtr>>(&a.value))for(const E* t:*p)if(self(self,t))return true;}return false;};
            if(connected(connected,ptr.get()))throw EvalError("unsupported connected operator "+ptr->className+" '"+ptr->name+"'");
        }
    }
};
