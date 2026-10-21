#pragma once
#include "source.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <numeric>

namespace pulse::source {
struct BakedSampleError { double position=0, normalDegrees=0; };

// Measure the same linear interpolation used by the flex playback helper.
// Missing sparse deltas mean the bind position/normal, not a missing vertex.
inline BakedSampleError BakedInterpolationError(const SrcMorphAnim& a,const SrcMorphAnim& sample,
        const SrcMorphAnim& b,const std::vector<SrcVertex>& vertices,double t) {
    const std::vector<SrcVertAnim>* arrays[3]={&a.vanims,&sample.vanims,&b.vanims};
    size_t cursors[3]={};BakedSampleError error;
    for(;;) {
        int index=std::numeric_limits<int>::max();
        for(int k=0;k<3;++k)if(cursors[k]<arrays[k]->size())index=std::min(index,(*arrays[k])[cursors[k]].vertex);
        if(index==std::numeric_limits<int>::max())break;
        SrcVertAnim deltas[3]{};
        for(int k=0;k<3;++k)if(cursors[k]<arrays[k]->size() && (*arrays[k])[cursors[k]].vertex==index)deltas[k]=(*arrays[k])[cursors[k]++];
        const auto& base=vertices.at(size_t(index)).normal;
        const double dx=(1-t)*deltas[0].pos.x+t*deltas[2].pos.x-deltas[1].pos.x;
        const double dy=(1-t)*deltas[0].pos.y+t*deltas[2].pos.y-deltas[1].pos.y;
        const double dz=(1-t)*deltas[0].pos.z+t*deltas[2].pos.z-deltas[1].pos.z;
        error.position=std::max(error.position,std::sqrt(dx*dx+dy*dy+dz*dz));
        const double nx=base.x+(1-t)*deltas[0].normal.x+t*deltas[2].normal.x;
        const double ny=base.y+(1-t)*deltas[0].normal.y+t*deltas[2].normal.y;
        const double nz=base.z+(1-t)*deltas[0].normal.z+t*deltas[2].normal.z;
        const double sx=base.x+deltas[1].normal.x,sy=base.y+deltas[1].normal.y,sz=base.z+deltas[1].normal.z;
        const double lengths=std::sqrt((nx*nx+ny*ny+nz*nz)*(sx*sx+sy*sy+sz*sz));
        const double degrees=lengths>0 ? std::acos(std::clamp((nx*sx+ny*sy+nz*sz)/lengths,-1.0,1.0))*180/3.14159265358979323846 : 180;
        error.normalDegrees=std::max(error.normalDegrees,degrees);
    }
    return error;
}

// Split at the worst actual vertex/normal sample until every retained segment
// meets both tolerances. This bounds the sampled reference, not an unknown
// continuous curve between reference samples. The caller preserves STEP clips.
inline std::vector<size_t> ReduceBakedSamples(std::vector<SrcMorphAnim>& samples,const Source& source,
        double positionTolerance,double normalTolerance,BakedSampleError& finalError) {
    std::vector<size_t> result;
    if(samples.empty())return result;
    for(auto& sample:samples)std::sort(sample.vanims.begin(),sample.vanims.end(),[](const auto& a,const auto& b){return a.vertex<b.vertex;});
    std::vector<bool> keep(samples.size());keep.front()=keep.back()=true;
    uint64_t work=0;
    std::vector<std::pair<size_t,size_t>> segments{{0,samples.size()-1}};
    auto ratio=[](double error,double tolerance){return tolerance>0?error/tolerance:(error>0?std::numeric_limits<double>::infinity():0);};
    while(!segments.empty()) {
        const auto segment=segments.back();segments.pop_back();const auto a=segment.first,b=segment.second;
        size_t worst=a;double largest=1;BakedSampleError segmentError;
        for(size_t i=a+1;i<b;++i) {
            // Pathological curves can require quadratic splitting. Retaining
            // the original samples remains exact and bounds reduction work.
            if((work+=source.vertex.size())>256ull*1024*1024) {
                result.resize(samples.size());std::iota(result.begin(),result.end(),0);finalError={};
                std::printf("BakeSceneTolerance: retained all samples after reaching the reduction work budget\n");
                return result;
            }
            const double t=(double(source.bakedTimes[i])-source.bakedTimes[a])/(double(source.bakedTimes[b])-source.bakedTimes[a]);
            const auto error=BakedInterpolationError(samples[a],samples[i],samples[b],source.vertex,t);
            const double score=std::max(ratio(error.position,positionTolerance),ratio(error.normalDegrees,normalTolerance));
            if(score>largest){largest=score;worst=i;}
            segmentError.position=std::max(segmentError.position,error.position);segmentError.normalDegrees=std::max(segmentError.normalDegrees,error.normalDegrees);
        }
        if(worst!=a){keep[worst]=true;segments.emplace_back(a,worst);segments.emplace_back(worst,b);}
        else {finalError.position=std::max(finalError.position,segmentError.position);finalError.normalDegrees=std::max(finalError.normalDegrees,segmentError.normalDegrees);}
    }
    for(size_t i=0;i<keep.size();++i)if(keep[i])result.push_back(i);
    return result;
}
}
