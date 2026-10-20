#include "dmxeval.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>
#include <type_traits>

namespace pulse::loader {
namespace {
namespace pm=math;
using E=dmx::Element;
struct EvalError:std::runtime_error { using std::runtime_error::runtime_error; };
enum class Kind { Float,Int,Bool,V2,V3,V4,Quat,QAngle,Matrix,Color,String,Time };
struct V { Kind kind=Kind::Float; std::array<float,16> v{}; std::string text; };
V scalar(float x) {return {Kind::Float,{x,0,0,0}};}
int width(Kind k){return k==Kind::String?0:k==Kind::Matrix?16:k==Kind::V2?2:(k==Kind::V3||k==Kind::QAngle)?3:(k==Kind::V4||k==Kind::Quat||k==Kind::Color)?4:1;}
void finite(const V& v) {for(int i=0;i<width(v.kind);++i)if(!std::isfinite(v.v[i]))throw EvalError("non-finite evaluated value");}
V value(const dmx::Attribute* a,int index=-1) {
    if(!a)throw EvalError("missing input attribute");
    const auto& v=a->value;
    if(index>=0) {
#define ARRAY_VALUE(T,K,N,...) if(const auto* p=std::get_if<std::vector<T>>(&v)){if(size_t(index)>=p->size())throw EvalError("array reference out of range");const auto x=(*p)[index];return {Kind::K,{__VA_ARGS__}};}
        ARRAY_VALUE(float,Float,1,x,0,0,0)
        ARRAY_VALUE(int32_t,Int,1,float(x),0,0,0)
        ARRAY_VALUE(bool,Bool,1,x?1.0f:0.0f,0,0,0)
        ARRAY_VALUE(dmx::Vector2,V2,2,x.x,x.y,0,0)
        ARRAY_VALUE(dmx::Vector3,V3,3,x.x,x.y,x.z,0)
        ARRAY_VALUE(dmx::Vector4,V4,4,x.x,x.y,x.z,x.w)
        ARRAY_VALUE(dmx::Quaternion,Quat,4,x.x,x.y,x.z,x.w)
        ARRAY_VALUE(dmx::QAngle,QAngle,3,x.x,x.y,x.z,0)
        ARRAY_VALUE(dmx::Color,Color,4,float(x.r),float(x.g),float(x.b),float(x.a))
        ARRAY_VALUE(dmx::Time,Time,1,x.seconds,0,0,0)
        if(const auto* p=std::get_if<std::vector<std::string>>(&v)){if(size_t(index)>=p->size())throw EvalError("array reference out of range");return {Kind::String,{},(*p)[index]};}
        if(const auto* p=std::get_if<std::vector<dmx::Matrix>>(&v)){if(size_t(index)>=p->size())throw EvalError("array reference out of range");V x{Kind::Matrix,{}};std::copy_n((*p)[index].m,16,x.v.begin());return x;}
#undef ARRAY_VALUE
        throw EvalError("unsupported array value type");
    }
    if(const auto* p=std::get_if<float>(&v))return scalar(*p);
    if(const auto* p=std::get_if<int32_t>(&v))return {Kind::Int,{float(*p),0,0,0}};
    if(const auto* p=std::get_if<bool>(&v))return {Kind::Bool,{*p?1.0f:0.0f,0,0,0}};
    if(const auto* p=std::get_if<dmx::Vector2>(&v))return {Kind::V2,{p->x,p->y,0,0}};
    if(const auto* p=std::get_if<dmx::Vector3>(&v))return {Kind::V3,{p->x,p->y,p->z,0}};
    if(const auto* p=std::get_if<dmx::Vector4>(&v))return {Kind::V4,{p->x,p->y,p->z,p->w}};
    if(const auto* p=std::get_if<dmx::Quaternion>(&v))return {Kind::Quat,{p->x,p->y,p->z,p->w}};
    if(const auto* p=std::get_if<dmx::QAngle>(&v))return {Kind::QAngle,{p->x,p->y,p->z}};
    if(const auto* p=std::get_if<dmx::Color>(&v))return {Kind::Color,{float(p->r),float(p->g),float(p->b),float(p->a)}};
    if(const auto* p=std::get_if<dmx::Time>(&v))return {Kind::Time,{p->seconds}};
    if(const auto* p=std::get_if<std::string>(&v))return {Kind::String,{},*p};
    if(const auto* p=std::get_if<dmx::Matrix>(&v)){V x{Kind::Matrix,{}};std::copy_n(p->m,16,x.v.begin());return x;}
    throw EvalError("unsupported animation value type for '"+a->name+"'");
}
int ticks(float sec) {
    const double t=std::floor(double(sec)*10000.0+0.5);
    if(!std::isfinite(t)||t<std::numeric_limits<int>::min()||t>std::numeric_limits<int>::max())throw EvalError("animation time out of range");
    return int(t);
}
int timeField(const E* e,const char* name) {
    const auto* a = e ? e->Get(name) : nullptr;
    // DMX model 1 names its integer-tick timeframe fields startTime,
    // durationTime and offsetTime; later models use typed time values.
    if (!a && e) a = e->Get(std::string(name) + "Time");
    if(a) {
        if(const auto* t=std::get_if<dmx::Time>(&a->value))return ticks(t->seconds);
        if(const auto* t=std::get_if<int32_t>(&a->value))return *t;
        throw EvalError(std::string("invalid time field ")+name);
    }
    return 0;
}
std::vector<int> keyTimes(const E* layer) {
    if(!layer)throw EvalError("null log layer");
    std::vector<int> t;
    if(const auto* p=layer->GetIntArray("times"))t.assign(p->begin(),p->end());
    else if(const auto* a=layer->Get("times")) {
        const auto* p=std::get_if<std::vector<dmx::Time>>(&a->value);
        if(!p)throw EvalError("invalid log times array");
        for(const auto& v:*p)t.push_back(ticks(v.seconds));
    }
    if(t.size()>1000000)throw EvalError("animation log exceeds 1000000 keys");
    for(size_t i=1;i<t.size();++i)if(t[i]<=t[i-1])throw EvalError("log key times must increase strictly");
    return t;
}
size_t arraySize(const dmx::Attribute* a) {
    if(!a)return 0;
    return std::visit([](const auto& v)->size_t {
        using T=std::decay_t<decltype(v)>;
        if constexpr(std::is_same_v<T,std::vector<float>>||std::is_same_v<T,std::vector<int32_t>>||std::is_same_v<T,std::vector<bool>>||std::is_same_v<T,std::vector<dmx::Vector2>>||std::is_same_v<T,std::vector<dmx::Vector3>>||std::is_same_v<T,std::vector<dmx::Vector4>>||std::is_same_v<T,std::vector<dmx::Quaternion>>||std::is_same_v<T,std::vector<dmx::QAngle>>||std::is_same_v<T,std::vector<dmx::Color>>||std::is_same_v<T,std::vector<dmx::Matrix>>||std::is_same_v<T,std::vector<dmx::Time>>||std::is_same_v<T,std::vector<std::string>>)return v.size();
        return 0;
    },a->value);
}
template<class T> T field(const E* e,const char* name,T fallback) {
    if(e)if(const auto* a=e->Get(name)) {
        if(const auto* p=std::get_if<T>(&a->value))return *p;
        throw EvalError(std::string("invalid curve field ")+name);
    }
    return fallback;
}
V zero(Kind kind) {V v{kind,{}};if(kind==Kind::Quat)v.v[3]=1;return v;}
V blend(V a,const V& b,float f) {
    if(a.kind==Kind::String||a.kind==Kind::Matrix)return a;
    if(a.kind==Kind::QAngle) {
        constexpr float r=3.14159265358979323846f/180.0f;
        pm::Quaternion x,y,q;pm::AngleQuaternion({a.v[2]*r,a.v[0]*r,a.v[1]*r},x);pm::AngleQuaternion({b.v[2]*r,b.v[0]*r,b.v[1]*r},y);
        pm::QuaternionSlerp(x,y,f,q);pm::RadianEuler e;pm::QuaternionAngles(q,e);a.v={e.y/r,e.z/r,e.x/r};return a;
    }
    if(a.kind==Kind::Time){a.v[0]=float(int(double(ticks(a.v[0]))*(1-f)+double(ticks(b.v[0]))*f))/10000.0f;return a;}
    if(a.kind==Kind::Quat) {
        pm::Quaternion q;pm::QuaternionSlerp({a.v[0],a.v[1],a.v[2],a.v[3]},{b.v[0],b.v[1],b.v[2],b.v[3]},f,q);pm::QuaternionNormalize(q);
        a.v={q.x,q.y,q.z,q.w};
    } else for(int j=0;j<width(a.kind);++j)a.v[j]=(1-f)*a.v[j]+f*b.v[j];
    if(a.kind==Kind::Color)for(int j=0;j<4;++j)a.v[j]=std::trunc(std::clamp(a.v[j],0.0f,255.0f));
    return a;
}
// Decode independent component streams once. Offsets and run coverage must be
// exact: accepting a truncated final run would hide corrupt motion as a hold.
std::vector<V> decompress(const dmx::Binary& data,size_t count,Kind kind) {
    if(kind!=Kind::V3&&kind!=Kind::Quat)throw EvalError("compressed DMX logs require Vector3 or Quaternion values");
    if(data.size()<32||!count)throw EvalError("invalid compressed DMX log header or key count");
    auto u32=[&](size_t p){return uint32_t(data[p])|(uint32_t(data[p+1])<<8)|(uint32_t(data[p+2])<<16)|(uint32_t(data[p+3])<<24);};
    auto f32=[&](size_t p){uint32_t bits=u32(p);float f;std::memcpy(&f,&bits,4);if(!std::isfinite(f))throw EvalError("non-finite compressed DMX scale/base");return f;};
    std::array<size_t,4> offsets{32,u32(24),u32(28),data.size()};
    for(int j=1;j<4;++j)if(offsets[j]<=offsets[j-1]||(offsets[j]&1)||offsets[j]>data.size())throw EvalError("invalid compressed DMX stream offsets");
    std::vector<V> values(count,V{kind,{}});
    for(int axis=0;axis<3;++axis) {
        const float scale=f32(axis*4),base=f32(12+axis*4);size_t p=offsets[axis],key=0,end=offsets[axis+1];
        while(key<count) {
            if(end-p<2)throw EvalError("truncated compressed DMX run");
            const unsigned valid=data[p++],total=data[p++];
            if(!valid||!total||valid>total||total>count-key)throw EvalError("invalid compressed DMX run counts");
            if(size_t(valid)*2>end-p)throw EvalError("truncated compressed DMX run values");
            float v=0;
            for(unsigned i=0;i<total;++i) {
                if(i<valid){const unsigned raw=unsigned(data[p])|(unsigned(data[p+1])<<8);p+=2;v=base+float(raw>=32768?int(raw)-65536:int(raw))*scale;}
                values[key++].v[axis]=v;
            }
        }
        if(p!=end)throw EvalError("compressed DMX stream has trailing data");
    }
    for(auto& v:values) {
        finite(v);
        if(kind==Kind::Quat){pm::Quaternion q;pm::AngleQuaternion({v.v[0],v.v[1],v.v[2]},q);v.v={q.x,q.y,q.z,q.w};finite(v);}
    }
    return values;
}
void curveType(int type,Kind kind) {
    if(type<0||(type&~0x0f0f))throw EvalError("unsupported DMX curve interpolation type");
    if(kind==Kind::Time)return;
    if(kind!=Kind::Float&&kind!=Kind::V3&&kind!=Kind::Quat)throw EvalError("DMX curve interpolation requires Float, Vector3, Quaternion or Time values");
    if(kind!=Kind::Float&&((type&255)==14||(type>>8)==14))throw EvalError("exponential-decay DMX curves require Float values");
}
float remapCurve(int mode,float f) {
    if(mode==2)return std::sin(1.5707963267948966f*f);
    if(mode==3)return 1-std::cos(1.5707963267948966f*f);
    if(mode==4||mode==10)return f*f*(3-2*f);
    return f;
}
struct CurvePoint {double time;V value;int type;};
// DmeTime_t exposes float seconds. Preserve that rounding before subtraction:
// a default edge one tick after the last key otherwise changes the tangent.
float curveSeconds(double t) {return float(t)*.0001f;}
V interpolateCurve(int mode,const std::array<CurvePoint,4>& points,float f) {
    const Kind kind=points[1].value.kind;
    if(kind==Kind::Time)return points[1].value; // reference generic Curve_Interpolate holds time values
    // Quaternion spline modes in DmeLog intentionally use ordinary SLERP.
    if(kind==Kind::Quat)return blend(points[1].value,points[2].value,mode>=2&&mode<=4?remapCurve(mode,f):f);
    if(mode==2||mode==3||mode==4||mode==6||mode==10)return blend(points[1].value,points[2].value,remapCurve(mode,f));
    if(mode==14)return blend(points[1].value,points[2].value,points[2].time>points[1].time?1-std::pow(.001f,f):0);
    V out=zero(kind);
    for(int j=0;j<width(kind);++j) {
        double p0=points[0].value.v[j],p1=points[1].value.v[j],p2=points[2].value.v[j],p3=points[3].value.v[j];
        const float dt=curveSeconds(points[2].time)-curveSeconds(points[1].time);
        const bool normalizeTime=mode==1||(kind==Kind::Float&&(mode==0||(mode>=7&&mode<=9)));
        if(normalizeTime&&dt!=0) {
            const float left=curveSeconds(points[1].time)-curveSeconds(points[0].time),right=curveSeconds(points[3].time)-curveSeconds(points[2].time);
            if(left!=0)p0=float(p1)+(float(p0)-float(p1))*(dt/left);
            if(right!=0)p3=float(p2)+(float(p3)-float(p2))*(dt/right);
        } else if(kind==Kind::Float&&mode==12) {
            // Scalar normalized Catmull uses distance in (seconds,value).
            const double distance=std::hypot(double(dt),p2-p1);
            const double left=std::hypot(double(curveSeconds(points[0].time)-curveSeconds(points[1].time)),p0-p1),right=std::hypot(double(curveSeconds(points[3].time)-curveSeconds(points[2].time)),p3-p2);
            p0=p1+(left?(p0-p1)*distance/left:0);p3=p2+(right?(p3-p2)*distance/right:0);
        }
        const double t=f,t2=t*t,t3=t2*t;
        double result;
        if(mode==5)result=((1-3*t+3*t2-t3)*p0+(4-6*t2+3*t3)*p1+(1+3*t+3*t2-3*t3)*p2+t3*p3)/6;
        else if(mode>=7&&mode<=9) {
            const double bias=mode==8?-1:mode==9?1:0,tension=.77,continuity=.77;
            const double m1=.5*(1-tension)*((1+continuity)*(1+bias)*(p1-p0)+(1-continuity)*(1-bias)*(p2-p1));
            const double m2=.5*(1-tension)*((1-continuity)*(1+bias)*(p2-p1)+(1+continuity)*(1-bias)*(p3-p2));
            result=(2*t3-3*t2+1)*p1+(t3-2*t2+t)*m1+(-2*t3+3*t2)*p2+(t3-t2)*m2;
        } else {
            const double a=-p0+p2,b=2*p0-5*p1+4*p2-p3,c=-p0+3*p1-3*p2+p3;
            result=kind==Kind::Float&&mode==13?.5*(a+2*b*t+3*c*t2):.5*(2*p1+a*t+b*t2+c*t3);
        }
        out.v[j]=float(result);
    }
    finite(out);return out;
}
struct Layer {const E* e;std::vector<int> times;std::vector<V> values;std::vector<int> curves;};
struct Log {
    const E* e=nullptr;const E* curve=nullptr;std::vector<Layer> layers;
    int defaultCurve=0,rightTime=0;float minimum=0,maximum=1;
    std::array<V,2> edgeValues{};std::array<int,2> edgeCurves{};
    Log()=default;
    explicit Log(const E* log):e(log) {
        if(!e)return;
        curve=field<dmx::ElementPtr>(e,"curveinfo",nullptr);
        if(curve) {
            defaultCurve=field<int32_t>(curve,"defaultCurveType",0);rightTime=timeField(curve,"rightEdgeTime");
            minimum=field<float>(curve,"minvalue",0);maximum=field<float>(curve,"maxvalue",1);
            if(!std::isfinite(minimum)||!std::isfinite(maximum)||minimum>maximum)throw EvalError("invalid DMX curve value bounds");
        }
        bool haveKind=false;Kind commonKind=Kind::Float;
        if(const auto* ls=e->GetElementArray("layers"))for(const auto* l:*ls) {
            auto ts=keyTimes(l);
            std::vector<V> vs;const auto* compressed=l->Get("compressed");
            const auto* binary=compressed?std::get_if<dmx::Binary>(&compressed->value):nullptr;
            if(compressed&&!binary)throw EvalError("invalid compressed DMX attribute type");
            if(binary&&!binary->empty()) {
                Kind kind=e->className=="DmeVector3Log"?Kind::V3:e->className=="DmeQuaternionLog"?Kind::Quat:Kind::Float;
                if(l->className!=e->className+"Layer")throw EvalError("compressed DMX log/layer type mismatch");
                if(const auto* a=l->Get("values"))if(a->type!=(kind==Kind::Quat?dmx::AttrType::QuaternionArray:dmx::AttrType::Vector3Array))throw EvalError("invalid compressed DMX values array type");
                if(arraySize(l->Get("values")))throw EvalError("compressed DMX log also contains values");
                vs=decompress(*binary,ts.size(),kind);
            } else {
                if(arraySize(l->Get("values"))!=ts.size())throw EvalError("log times/values count mismatch");
                for(size_t i=0;i<ts.size();++i){V v=value(l->Get("values"),int(i));finite(v);vs.push_back(v);}
            }
            if(!vs.empty()) {
                if(haveKind&&commonKind!=vs[0].kind)throw EvalError("DMX log layers have different value types");
                haveKind=true;commonKind=vs[0].kind;
            }
            auto curves=field<std::vector<int32_t>>(l,"curvetypes",{});
            if(!curves.empty()&&curves.size()!=ts.size())throw EvalError("log times/curvetypes count mismatch");
            if(curve&&!vs.empty()&&(vs[0].kind==Kind::Float||vs[0].kind==Kind::V3||vs[0].kind==Kind::Quat||vs[0].kind==Kind::Time)) {
                const Kind kind=vs[0].kind;curveType(defaultCurve,kind);
                for(int type:curves)curveType(type,kind);
                const bool useEdge=field<bool>(curve,"useEdgeInfo",false);
                V fallback=curve->Get("defaultEdgeZeroValue")?value(curve->Get("defaultEdgeZeroValue")):zero(kind);
                if(fallback.kind!=kind)throw EvalError("DMX curve edge value type mismatch");finite(fallback);
                for(int side=0;side<2;++side) {
                    const char* activeName=side?"rightEdgeActive":"leftEdgeActive";const char* valueName=side?"rightEdgeValue":"leftEdgeValue";
                    const bool active=field<bool>(curve,activeName,false);
                    V edge=curve->Get(valueName)?value(curve->Get(valueName)):zero(kind);
                    if(edge.kind!=kind)throw EvalError("DMX curve edge value type mismatch");finite(edge);
                    edgeValues[side]=useEdge?(active?edge:fallback):zero(kind);
                    const int type=field<int32_t>(curve,side?"rightEdgeCurveType":"leftEdgeCurveType",0);curveType(type,kind);
                    edgeCurves[side]=active&&type?type:defaultCurve;
                }
            }
            if(const auto* a=l->Get("noninterpolatedsegments")) {
                const auto* p=std::get_if<std::vector<bool>>(&a->value);
                if(!p||(!p->empty()&&p->size()!=ts.size()))throw EvalError("invalid noninterpolatedsegments array");
            }
            layers.push_back({l,std::move(ts),std::move(vs),std::move(curves)});
        }
    }
    bool hasKeys()const {for(const auto& l:layers)if(!l.times.empty())return true;return false;}
    bool hasDefault()const {return e&&e->GetBool("usedefaultvalue",false);}
    V curveSample(const Layer& l,int t,int k)const {
        if(rightTime&&t>rightTime)return l.values[0].kind==Kind::Float?edgeValues[1]:zero(l.values[0].kind);
        if(!rightTime&&k>=int(l.times.size())-1)return l.values.back();
        std::array<CurvePoint,4> points;
        for(int j=0;j<4;++j) {
            const int index=k+j-1;
            if(index<0)points[j]={0,edgeValues[0],edgeCurves[0]};
            else if(size_t(index)>=l.times.size())points[j]={rightTime?double(rightTime):double(l.times.back())+1,edgeValues[1],edgeCurves[1]};
            else points[j]={double(l.times[index]),l.values[index],l.curves.empty()||!l.curves[index]?defaultCurve:l.curves[index]};
        }
        const float f=points[2].time>points[1].time?(curveSeconds(t)-curveSeconds(points[1].time))/(curveSeconds(points[2].time)-curveSeconds(points[1].time)):0;
        if(!std::isfinite(f))throw EvalError("DMX curve times exceed interpolation precision");
        const int outgoing=points[1].type&255,incoming=points[2].type>>8;
        V result;
        if(outgoing==15)result=points[1].value;
        else if(incoming==15)result=points[2].value;
        else {
            result=interpolateCurve(outgoing,points,f);
            if(outgoing!=incoming)result=blend(result,interpolateCurve(incoming,points,f),f);
        }
        finite(result);
        if(result.kind==Kind::Float)result.v[0]=std::max(minimum,std::min(maximum,result.v[0]));
        return result;
    }
    V sample(int t)const {
        if(layers.empty()) {
            if(e&&e->GetBool("usedefaultvalue",false))return value(e->Get("defaultvalue"));
            throw EvalError("animation channel has no log layers");
        }
        // Channel playback holds outside the union of the log's layer ranges.
        int first=std::numeric_limits<int>::max(),last=std::numeric_limits<int>::min();
        for(const auto& candidate:layers)if(!candidate.times.empty()){first=std::min(first,candidate.times.front());last=std::max(last,candidate.times.back());}
        if(first<=last)t=std::max(first,std::min(t,last));
        const Layer* l=&layers.front();
        for(auto it=layers.rbegin();it!=layers.rend();++it)if(!it->times.empty()&&t>=it->times.front()&&t<=it->times.back()){l=&*it;break;}
        if(l->times.empty()) {
            if(e->GetBool("usedefaultvalue",false))return value(e->Get("defaultvalue"));
            throw EvalError("empty animation log without a default value");
        }
        const auto upper=std::upper_bound(l->times.begin(),l->times.end(),t);
        int k=int(upper-l->times.begin())-1;
        if(curve&&(l->values[0].kind==Kind::Float||l->values[0].kind==Kind::V3||l->values[0].kind==Kind::Quat||l->values[0].kind==Kind::Time))return curveSample(*l,t,k);
        k=std::max(0,k);
        V a=l->values[k];
        if(t<l->times.front()||size_t(k+1)>=l->times.size()||a.kind==Kind::Int||a.kind==Kind::Bool)return a;
        if(const auto* attr=l->e->Get("noninterpolatedsegments"))if(const auto* p=std::get_if<std::vector<bool>>(&attr->value))if(!p->empty()&&(*p)[k])return a;
        const V b=l->values[k+1];
        const float f=float((double(t)-l->times[k])/(double(l->times[k+1])-l->times[k]));
        return blend(a,b,f);
    }
};

// Small deterministic scalar expression evaluator. Functions outside this
// supported grammar fail, so no stale result value is silently reused.
class Expression {
    const std::string& s;size_t p=0;std::function<float(const std::string&)> get;
    void ws(){while(p<s.size()&&std::isspace(static_cast<unsigned char>(s[p])))++p;}
    bool eat(const char* t){ws();size_t n=std::char_traits<char>::length(t);if(s.compare(p,n,t)!=0)return false;p+=n;return true;}
    float atom(){
        if(eat("(")){float v=cond();if(!eat(")"))throw EvalError("missing expression ')' ");return v;}
        ws();if(p>=s.size())throw EvalError("incomplete expression");
        if(std::isdigit(static_cast<unsigned char>(s[p]))||s[p]=='.'){char* end=nullptr;float v=std::strtof(s.c_str()+p,&end);if(end==s.c_str()+p)throw EvalError("bad number");p=size_t(end-s.c_str());return v;}
        const size_t start=p;while(p<s.size()&&(std::isalnum(static_cast<unsigned char>(s[p]))||s[p]=='_'))++p;
        if(p==start)throw EvalError("unexpected expression token");
        std::string name=s.substr(start,p-start);
        if(!eat("("))return get(name);
        std::vector<float> a;if(!eat(")")){do{a.push_back(cond());}while(eat(","));if(!eat(")"))throw EvalError("missing function ')' ");}
        if(a.size()==1){float x=a[0];
            if(name=="abs")return std::fabs(x);if(name=="sqr")return x*x;if(name=="sqrt")return std::sqrt(x);
            if(name=="sin")return std::sin(x);if(name=="cos")return std::cos(x);if(name=="tan")return std::tan(x);
            if(name=="asin")return std::asin(x);if(name=="acos")return std::acos(x);if(name=="atan")return std::atan(x);
            if(name=="floor")return std::floor(x);if(name=="ceil")return std::ceil(x);if(name=="round")return std::floor(x+0.5f);
            if(name=="exp")return std::exp(x);if(name=="log")return std::log(x);}
        if(a.size()==2){if(name=="min")return std::min(a[0],a[1]);if(name=="max")return std::max(a[0],a[1]);if(name=="pow")return std::pow(a[0],a[1]);if(name=="atan2")return std::atan2(a[0],a[1]);}
        if(a.size()==3){if(name=="clamp")return std::max(a[1],std::min(a[0],a[2]));if(name=="inrange")return a[0]>=a[1]&&a[0]<=a[2];if(name=="lerp"||name=="elerp"){float f=a[0];if(name=="elerp")f=f*f*(3-2*f);return (1-f)*a[1]+f*a[2];}}
        if(a.size()==5&&name=="rescale")return a[3]+(a[0]-a[1])/(a[2]-a[1])*(a[4]-a[3]);
        throw EvalError("unsupported expression function or arity: "+name);
    }
    float unary(){if(eat("+"))return unary();if(eat("-"))return -unary();if(eat("!"))return !unary();return atom();}
    float mul(){float a=unary();for(;;){if(eat("*"))a*=unary();else if(eat("/"))a/=unary();else if(eat("%"))a=std::fmod(a,unary());else return a;}}
    float add(){float a=mul();for(;;){if(eat("+"))a+=mul();else if(eat("-"))a-=mul();else return a;}}
    float compare(){float a=add();for(;;){if(eat("<="))a=a<=add();else if(eat(">="))a=a>=add();else if(eat("<"))a=a<add();else if(eat(">"))a=a>add();else return a;}}
    float eq(){float a=compare();for(;;){if(eat("=="))a=a==compare();else if(eat("!="))a=a!=compare();else return a;}}
    float both(){float a=eq();while(eat("&&")){float b=eq();a=bool(a)&&bool(b);}return a;}
    float either(){float a=both();while(eat("||")){float b=both();a=bool(a)||bool(b);}return a;}
    float cond(){float a=either();if(eat("?")){float b=cond();if(!eat(":"))throw EvalError("missing expression ':'");float c=cond();return a?b:c;}return a;}
public:
    Expression(const std::string& expression,std::function<float(const std::string&)> lookup):s(expression),get(std::move(lookup)){}
    float evaluate(){float v=cond();ws();if(p!=s.size())throw EvalError("unsupported expression token");if(!std::isfinite(v))throw EvalError("non-finite expression result");return v;}
};

struct Key {
    const E* e=nullptr;std::string attr;int index=-1;
    bool operator<(const Key& b)const {if(e!=b.e)return std::less<const E*>{}(e,b.e);return std::tie(attr,index)<std::tie(b.attr,b.index);}
};
Key key(const E* e,const std::string& attr,int index=0) {
    if(!e||attr.empty())throw EvalError("invalid attribute reference");
    const auto* a=e->Get(attr);
    return {e,attr,a&&dmx::IsArrayType(a->type)?index:-1};
}
Key reference(const E* e) {
    if(!e||!e->GetString("attribute"))throw EvalError("invalid DmeAttributeReference");
    return key(e->GetElement("element"),*e->GetString("attribute"),e->GetInt("index",0));
}
#include "dmxeval_graph.inc"
int frameAt(int t,float fps){
    const double frame=std::floor((double(t)+1.0)*double(fps)/10000.0);
    if(frame<std::numeric_limits<int>::min()||frame>std::numeric_limits<int>::max())throw EvalError("animation frame index out of range");
    return int(frame);
}
} // namespace

// Resolve the finite skeletal portion of a clip hierarchy. Film/shot clips
// compose their timeframe with channel clips; camera/audio/effect tracks have
// no channels and therefore contribute no bone output.
static std::vector<ClipPath> CollectClips(const E* root) {
    std::vector<ClipPath> result;std::set<const E*> stack;
    auto walk=[&](auto&& self,const E* e,std::vector<const E*> path,int depth)->void {
        if(!e)return;if(depth>128||!stack.insert(e).second)throw EvalError("cyclic or excessively nested clip hierarchy");
        const bool clip=e->className.find("Clip")!=std::string::npos||e->Get("timeFrame");
        if(clip)path.push_back(e);
        if(e->GetElementArray("channels"))result.push_back({e,path});
        for(const char* name:{"trackGroups","tracks","children","clips","shots"})if(const auto* children=e->GetElementArray(name))for(const E* child:*children) {
            if(!child)throw EvalError("null clip/track entry");
            if(name==std::string("children")&&child->className.find("Clip")==std::string::npos&&child->className.find("Track")==std::string::npos)continue;
            if(!child->GetBool("muted",false)&&!child->GetBool("mute",false))self(self,child,path,depth+1);
        }
        for(const char* key:{"subClipTrackGroup","filmTrackGroup"})if(const E* group=e->GetElement(key))self(self,group,path,depth+1);
        stack.erase(e);
    };
    walk(walk,root,{},0);return result;
}

bool CaptureDmxRig(const dmx::Datamodel& dm,float scale,DmxRigDefinition& out,std::string* error) {
    try {
        out={};out.scale=scale;out.identity=&dm;
        const auto* constraints=dm.root?dm.root->GetElementArray("constraints"):nullptr;if(!constraints||constraints->empty())return true;
        auto clone=std::make_shared<dmx::Datamodel>();clone->encoding=dm.encoding;clone->encoding_version=dm.encoding_version;clone->format=dm.format;clone->format_version=dm.format_version;
        std::map<const E*,E*> remap;
        for(const auto& e:dm.elements){E* copy=clone->CreateElement(e->id,e->className);copy->name=e->name;copy->attributes=e->attributes;remap[e.get()]=copy;}
        for(auto& e:clone->elements)for(auto& a:e->attributes){if(auto p=std::get_if<dmx::ElementPtr>(&a.value))*p=*p?remap.at(*p):nullptr;else if(auto p=std::get_if<std::vector<dmx::ElementPtr>>(&a.value))for(auto& q:*p)q=q?remap.at(q):nullptr;}
        clone->root=remap.at(dm.root);out.document=clone;
        const E* skeleton=dm.root->GetElement("skeleton");if(!skeleton)skeleton=dm.root->GetElement("model");
        std::map<const E*,const E*> parents;for(const auto& e:dm.elements)if(const auto* children=e->GetElementArray("children"))for(const E* child:*children)if(child&&child->GetElement("transform"))parents[child]=e.get()==skeleton?nullptr:e->GetElement("transform")?e.get():nullptr;
        std::map<const E*,bool> needed;
        auto addDag=[&](auto&& self,const E* dag,bool output)->void{if(!dag||!dag->GetElement("transform"))throw EvalError("missing rig DAG/transform");if(needed.count(dag)){needed[dag]|=output;return;}needed[dag]=output;if(parents[dag])self(self,parents[dag],false);};
        for(const E* op:*constraints) {
            if(!op||!rigClass(op->className))throw EvalError("unsupported operator in constraints");if(op->GetInt("mode",0))throw EvalError("reverse rig mode is not supported");out.operatorIds.push_back(dmx::GuidToString(op->id));
            if(op->className=="DmeRigIKConstraintOperator")for(const char* joint:{"startJoint","midJoint","endJoint"}){const E* holder=op->GetElement(joint);addDag(addDag,holder?holder->GetElement("target"):nullptr,std::string(joint)!="endJoint");}
            else if(op->className=="DmeRigTwistConstraintOperator"){const auto* ss=op->GetElementArray("twistJoints");if(!ss||ss->empty())throw EvalError("Twist has no slaves");for(const E* holder:*ss)addDag(addDag,holder?holder->GetElement("target"):nullptr,true);}
            else {const E* holder=op->GetElement("slave");addDag(addDag,holder?holder->GetElement("target"):nullptr,true);}
            if(const auto* ts=op->GetElementArray("targets"))for(const E* holder:*ts)addDag(addDag,holder?holder->GetElement("target"):nullptr,false);
            for(const char* parameter:{"upSpaceTarget","pvTarget"})if(const E* dag=op->GetElement(parameter))addDag(addDag,dag,false);
            std::vector<const E*> outputs;
            if(op->className=="DmeRigIKConstraintOperator"){outputs.push_back(op->GetElement("startJoint")->GetElement("target"));outputs.push_back(op->GetElement("midJoint")->GetElement("target"));}
            else if(op->className=="DmeRigTwistConstraintOperator"){for(const E* holder:*op->GetElementArray("twistJoints"))outputs.push_back(holder->GetElement("target"));}
            else outputs.push_back(op->GetElement("slave")->GetElement("target"));
            for(const E* output:outputs){
                if(const auto* ts=op->GetElementArray("targets"))for(const E* holder:*ts)out.dependencies.emplace_back(output->name,holder->GetElement("target")->name);
                for(const char* parameter:{"upSpaceTarget","pvTarget"})if(const E* dag=op->GetElement(parameter))out.dependencies.emplace_back(output->name,dag->name);
            }

        }
        std::set<std::string> names;for(const auto& item:needed){if(item.first->name.empty()||!names.insert(item.first->name).second)throw EvalError("duplicate or empty rig bone name");out.bones.push_back({item.first->name,item.first->name,-1,item.second});}
        Graph validate(*clone,{}); // validates structural references without evaluating an authored bind pose
        return true;
    }catch(const std::exception& e){if(error)*error=std::string("DMX rig capture: ")+e.what();return false;}
}

bool EvaluateDmxRigFrame(const DmxRigDefinition& rig,const std::map<std::string,math::matrix3x4>& authoredWorld,
    std::map<std::string,math::matrix3x4>& solvedWorld,std::string* error) {
    try {if(!rig.document){solvedWorld.clear();return true;}Graph graph(*rig.document,{});graph.frame(0,&authoredWorld);graph.checkUnsupported(*rig.document);solvedWorld=graph.rigWorlds();return true;}
    catch(const std::exception& e){if(error)*error=std::string("DMX rig evaluation: ")+e.what();return false;}
}

bool EvaluateDmxAnimations(const dmx::Datamodel& dm,const dmx::Element* root,
    const std::vector<const dmx::Element*>& transforms,float scale,source::Source& out,std::string* error) {
    try {
        if(!root)return true;std::vector<const E*> roots;std::set<const E*> unique;
        auto append=[&](const E* e){if(e&&unique.insert(e).second)roots.push_back(e);};
        const E* list=root->GetElement("animationList");if(!list&&root->GetElementArray("animations"))list=root;
        if(list)if(const auto* animations=list->GetElementArray("animations"))for(const E* e:*animations){if(!e)throw EvalError("null animation clip");append(e);}
        if(root->className.find("Clip")!=std::string::npos)append(root);
        for(const char* key:{"activeClip","filmClip","movie"})append(root->GetElement(key));
        if(roots.empty()&&(root->GetElementArray("trackGroups")||root->GetElementArray("channels")))append(root);
        // Selection throughout the compiler is case-insensitive, including the
        // reserved BindPose clip. Use that same equivalence for uniqueness.
        auto folded=[](std::string name){for(char& c:name)c=char(std::tolower(static_cast<unsigned char>(c)));return name;};
        std::set<std::string> names;for(const auto& a:out.anims)names.insert(folded(a.name));
        for(const E* clip:roots) {
            const auto clips=CollectClips(clip);if(clips.empty())continue;
            source::SourceAnim anim;anim.name=clip->name;if(anim.name.empty())anim.name="animation";
            if(!names.insert(folded(anim.name)).second)throw EvalError("duplicate or reserved animation name (case-insensitive) '"+anim.name+"'");
            float fps=float(clip->GetInt("frameRate",0));if(fps<=0){fps=clip->GetFloat("frameRate",30);if(!std::isfinite(fps))throw EvalError("invalid animation frame rate");if(fps<=0)fps=30;}
            if(fps>10000)throw EvalError("invalid animation frame rate: exceeds 10000");
            anim.sampleFps=fps;
            const E* tf=clip->GetElement("timeFrame");const int start=timeField(tf,"start"),duration=timeField(tf,"duration");if(duration<0||int64_t(start)+duration>std::numeric_limits<int>::max())throw EvalError("invalid clip duration");
            anim.startframe=frameAt(start,fps);anim.endframe=frameAt(start+duration,fps);const int64_t count=std::max<int64_t>(1,int64_t(anim.endframe)-anim.startframe+1);if(count>100000)throw EvalError("DMX animation exceeds 100000 frames");anim.numframes=int(count);
            Graph graph(dm,clips);anim.frames.resize(anim.numframes);
            for(int f=0;f<anim.numframes;++f) {
                const double offset=std::floor(double(f)*10000.0/double(fps)+0.5);
                if(offset>std::numeric_limits<int>::max())throw EvalError("animation sample time out of range");
                const int64_t step = fps == std::floor(fps) ?
                    int64_t(f/int(fps))*10000+ticks(float(f%int(fps))/fps) : int64_t(offset);
                const int64_t time=int64_t(start)+step;if(time<std::numeric_limits<int>::min()||time>std::numeric_limits<int>::max())throw EvalError("animation sample time out of range");
                graph.frame(int(time));auto& frame=anim.frames[f];frame.resize(out.numbones);
                for(size_t b=0;b<transforms.size();++b){const V p=graph.read(key(transforms[b],"position"),false),q=graph.read(key(transforms[b],"orientation"),false);if(p.kind!=Kind::V3||q.kind!=Kind::Quat)throw EvalError("bone pose has an invalid value type");finite(p);const auto rotation=normalized({q.v[0],q.v[1],q.v[2],q.v[3]});const auto m=pm::QuaternionMatrix(rotation,{p.v[0],p.v[1],p.v[2]});pm::MatrixAngles(m,frame[b].rot,frame[b].pos);frame[b].pos=mul(frame[b].pos,scale);finite(vectorValue(frame[b].pos));}
                graph.checkUnsupported(dm);for(const auto& id:graph.rigIds())if(std::find(anim.bakedRigOperators.begin(),anim.bakedRigOperators.end(),id)==anim.bakedRigOperators.end())anim.bakedRigOperators.push_back(id);
            }
            out.anims.push_back(std::move(anim));
        }
        return true;
    }catch(const std::exception& e){if(error)*error=std::string("DMX animation evaluation: ")+e.what();return false;}
}
} // namespace pulse::loader
