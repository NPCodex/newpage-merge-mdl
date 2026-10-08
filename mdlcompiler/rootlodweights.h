#pragma once
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <tuple>
#include <vector>

namespace pulse::compile {
// Immutable spatial index over the complete root mesh. Source-order tie breaks
// are independent of tree traversal; UV/normal seams keep their own skinning.
template<class Vertices> class RootLodWeights {
    const Vertices& vertices;
    struct Node { int vertex,left=-1,right=-1,axis; };
    std::vector<Node> nodes;
    std::vector<int> order;
    template<class V> static double Axis(const V& v,int axis) {
        return axis==0?v.position.x:axis==1?v.position.y:v.position.z;
    }
    int Build(int begin,int end,int depth) {
        if(begin==end)return -1;
        const int axis=depth%3,mid=begin+(end-begin)/2;
        std::nth_element(order.begin()+begin,order.begin()+mid,order.begin()+end,
            [&](int a,int b){return std::make_pair(Axis(vertices[a],axis),a)<std::make_pair(Axis(vertices[b],axis),b);});
        const int index=static_cast<int>(nodes.size());nodes.push_back({order[mid],-1,-1,axis});
        const int left=Build(begin,mid,depth+1),right=Build(mid+1,end,depth+1);
        nodes[index].left=left;nodes[index].right=right;return index;
    }
    template<class V> auto Error(const V& v,int i) const {
        const auto& r=vertices[i];
        const double x=double(v.position.x)-r.position.x,y=double(v.position.y)-r.position.y,z=double(v.position.z)-r.position.z;
        const double u=double(v.texcoord.x)-r.texcoord.x,w=double(v.texcoord.y)-r.texcoord.y;
        const double vn=std::sqrt(double(v.normal.x)*v.normal.x+double(v.normal.y)*v.normal.y+double(v.normal.z)*v.normal.z);
        const double rn=std::sqrt(double(r.normal.x)*r.normal.x+double(r.normal.y)*r.normal.y+double(r.normal.z)*r.normal.z);
        const double normal=vn>0&&rn>0?1-(double(v.normal.x)*r.normal.x+double(v.normal.y)*r.normal.y+double(v.normal.z)*r.normal.z)/(vn*rn):2;
        return std::make_tuple(x*x+y*y+z*z,u*u+w*w,normal,-i);
    }
    template<class V> void Search(int node,const V& v,int& best) const {
        if(node<0)return;
        const auto& n=nodes[node];
        if(best<0||Error(v,n.vertex)<Error(v,best))best=n.vertex;
        const double delta=Axis(v,n.axis)-Axis(vertices[n.vertex],n.axis);
        Search(delta<0?n.left:n.right,v,best);
        if(delta*delta<=std::get<0>(Error(v,best)))Search(delta<0?n.right:n.left,v,best);
    }
    template<class V,class Visitor> void Within(int node,const V& v,double radius2,Visitor& visitor) const {
        if(node<0)return;
        const auto& n=nodes[node];
        if(std::get<0>(Error(v,n.vertex))<=radius2)visitor(n.vertex);
        const double delta=Axis(v,n.axis)-Axis(vertices[n.vertex],n.axis);
        Within(delta<0?n.left:n.right,v,radius2,visitor);
        if(delta*delta<=radius2)Within(delta<0?n.right:n.left,v,radius2,visitor);
    }
public:
    explicit RootLodWeights(const Vertices& v,bool enabled,int begin=0,int end=-1):vertices(v) {
        if(!enabled)return;
        if(end<0)end=static_cast<int>(v.size());
        order.resize(end-begin);std::iota(order.begin(),order.end(),begin);
        nodes.reserve(order.size());Build(0,static_cast<int>(order.size()),0);
    }
    template<class V> int Nearest(const V& v) const {int best=-1;Search(nodes.empty()?-1:0,v,best);return best;}
    template<class V,class Visitor> void VisitWithin(const V& v,double radius,Visitor visitor) const {
        Within(nodes.empty()?-1:0,v,radius*radius,visitor);
    }
};
}
