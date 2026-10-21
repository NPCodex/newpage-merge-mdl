/* Targeted, strict static USD composition for the maintained importer.
 * SPDX-License-Identifier: BSD-3-Clause
 * Unsupported arcs fail explicitly instead of importing a partial scene. */
#pragma once
#include "composition.hh"
#include "tinyusdz.hh"
#include <assimp/IOSystem.hpp>
#include <assimp/IOStream.hpp>
#include <assimp/Exceptional.h>
#include <filesystem>
#include <algorithm>
#include <memory>
#include <functional>
#include <map>
#include <set>

namespace Assimp {
class StaticUsdComposition {
    using Prim=tinyusdz::PrimSpec;
    using Layer=tinyusdz::Layer;
    using Selections=std::map<std::string,std::string>;
    IOSystem& io;
    std::map<std::string,Layer> layers;
    std::set<std::string> active;
    size_t expanded=0;
    std::string warnings;

    static std::string Canonical(const std::string& path) {
        std::error_code ec;const auto absolute=std::filesystem::absolute(std::filesystem::u8path(path),ec);
        if(ec)throw DeadlyImportError("USD invalid asset path: ",path);
        const auto canonical=std::filesystem::weakly_canonical(absolute,ec);
        return (ec?absolute.lexically_normal():canonical).u8string();
    }
    const Layer& Read(const std::string& path) {
        auto found=layers.find(path);if(found!=layers.end())return found->second;
        if(layers.size()>=128)throw DeadlyImportError("USD composition exceeds 128 source layers");
        auto close=[&](IOStream* stream){io.Close(stream);};
        std::unique_ptr<IOStream,decltype(close)> stream(io.Open(path,"rb"),close);
        if(!stream)throw DeadlyImportError("USD referenced asset not found: ",path);
        const auto size=stream->FileSize();if(size>512ull*1024*1024)throw DeadlyImportError("USD layer exceeds 512 MiB: ",path);
        std::vector<uint8_t> bytes(size);
        if(size && stream->Read(bytes.data(),1,size)!=size)throw DeadlyImportError("USD incomplete layer read: ",path);
        Layer layer;std::string error,warn;
        if(!tinyusdz::LoadLayerFromMemory(bytes.data(),bytes.size(),path,&layer,&warn,&error))
            throw DeadlyImportError("USD layer parse failed: ",path,": ",error);
        warnings+=warn;
        // The bundled library does not fully implement sublayer strengths and
        // offsets; do not silently flatten those arcs with incorrect ordering.
        if(!layer.metas().subLayers.empty())throw DeadlyImportError("USD subLayers composition is not supported; flatten subLayers before import: ",path);
        return layers.emplace(path,std::move(layer)).first->second;
    }
    // Merge the weaker referenced/variant opinions while preserving local
    // properties AND local-only children (the bundled helper loses the latter).
    static void Inherit(Prim& local,const Prim& weak) {
        if(local.specifier()==tinyusdz::Specifier::Over)local.specifier()=weak.specifier();
        if(local.typeName().empty() || local.typeName()=="Model")local.typeName()=weak.typeName();
        if(local.metas().references && weak.metas().references && !local.metas().references.value().second.empty() && !weak.metas().references.value().second.empty())
            throw DeadlyImportError("USD multiple contributed reference opinions are not supported; flatten this prim: ",local.name());
        local.metas().update_from(weak.metas(),false);
        for(const auto& property:weak.props())local.props().emplace(property);
        for(const auto& child:weak.children()) {
            auto found=std::find_if(local.children().begin(),local.children().end(),[&](const auto& current){return current.name()==child.name();});
            if(found==local.children().end())local.children().push_back(child);else Inherit(*found,child);
        }
    }
    Prim Compose(Prim prim,const std::string& file,const std::string& primPath,
                 const Selections& overrideSelections={},bool referenced=false,
                 nonstd::optional<bool> overrideInstanceable=nonstd::nullopt,
                 nonstd::optional<bool> overrideActive=nonstd::nullopt,
                 const std::set<std::string>& knownSelections={}) {
        if(active.size()>=64 || ++expanded>65536)throw DeadlyImportError("USD composition exceeds depth/prim budget at ",file,primPath);
        const auto identity=file+"|"+primPath;
        if(!active.insert(identity).second)throw DeadlyImportError("USD cyclic reference at ",file,primPath);
        struct Leave {std::set<std::string>& active;std::string id;~Leave(){active.erase(id);}} leave{active,identity};
        if(overrideInstanceable)prim.metas().instanceable=overrideInstanceable;
        if(overrideActive)prim.metas().active=overrideActive;
        auto inactivePrim=[&]() {Prim inactive(tinyusdz::Specifier::Def,"Xform",prim.name());inactive.metas().active=false;return inactive;};
        if(prim.metas().active && !prim.metas().active.value()) {
            return inactivePrim();
        }
        if(prim.metas().payload || prim.metas().inherits || prim.metas().specializes || prim.metas().clips)
            throw DeadlyImportError("USD unsupported payload/inherits/specializes/value-clips composition at ",file,primPath);
        if(prim.typeName()=="PointInstancer")throw DeadlyImportError("USD PointInstancer is not supported; expand instances before import: ",file,primPath);
        if(referenced && (prim.typeName()=="Skeleton" || prim.typeName()=="SkelRoot" || prim.typeName()=="SkelAnimation"))
            throw DeadlyImportError("USD skeletal reference remapping is not supported; flatten the skeleton before import: ",file,primPath);
        Selections selections=prim.metas().variants?prim.metas().variants.value():Selections{};
        for(const auto& selection:overrideSelections)selections[selection.first]=selection.second;
        Selections unresolved=selections;
        auto resolvedSelections=knownSelections;
        std::vector<Prim> selectedVariants;
        std::vector<std::pair<std::string,std::string>> orderedSelections;
        auto remainingSelections=selections;
        if(prim.metas().variantSets)for(const auto& name:prim.metas().variantSets.value().second) {
            const auto selected=remainingSelections.find(name);
            if(selected!=remainingSelections.end()){orderedSelections.push_back(*selected);remainingSelections.erase(selected);}
        }
        for(const auto& selected:remainingSelections)orderedSelections.push_back(selected);
        // Apply only explicitly selected variants. An unselected set contributes
        // no opinions, matching USD; a nonexistent authored selection is an error.
        for(const auto& selection:orderedSelections) {
            auto set=prim.variantSets().find(selection.first);if(set==prim.variantSets().end())continue;
            const auto choice=set->second.variantSet.find(selection.second);
            if(choice==set->second.variantSet.end())throw DeadlyImportError("USD variant selection not found: ",selection.first,"=",selection.second," at ",file,primPath);
            if(!choice->second.variantSets().empty())throw DeadlyImportError("USD nested variant sets are not supported; flatten the selected variant: ",file,primPath);
            selectedVariants.push_back(choice->second);Inherit(prim,choice->second);unresolved.erase(selection.first);
            resolvedSelections.insert(selection.first);
        }
        prim.variantSets().clear();prim.metas().variantSets.reset();prim.metas().variants.reset();
        if(prim.metas().active && !prim.metas().active.value())return inactivePrim();
        // OpenUSD excludes direct local child opinions from an instance's
        // prototype. Children supplied by selected variants/references remain.
        auto discardDirectChildren=[&]() {
            prim.children().clear();
            for(const auto& variant:selectedVariants)for(const auto& child:variant.children()) {
                auto found=std::find_if(prim.children().begin(),prim.children().end(),[&](const auto& item){return item.name()==child.name();});
                if(found==prim.children().end())prim.children().push_back(child);else Inherit(*found,child);
            }
        };
        if(prim.metas().instanceable && prim.metas().instanceable.value() &&
           ((prim.metas().references && !prim.metas().references.value().second.empty()) || !selectedVariants.empty()))discardDirectChildren();
        if(prim.metas().references) {
            const auto references=prim.metas().references.value();prim.metas().references.reset();
            using Qual=tinyusdz::ListEditQual;
            if(references.first!=Qual::ResetToExplicit && references.first!=Qual::Prepend && references.first!=Qual::Append && references.first!=Qual::Add)
                throw DeadlyImportError("USD unsupported reference list edit at ",file,primPath);
            if(references.second.size()>1)throw DeadlyImportError("USD multiple reference arcs on one prim are not supported; flatten this prim: ",file,primPath);
            for(const auto& reference:references.second) {
                if(reference.layerOffset._offset!=0 || reference.layerOffset._scale!=1)
                    throw DeadlyImportError("USD reference time offsets are not supported: ",file,primPath);
                const auto asset=reference.asset_path.GetAssetPath();
                const auto targetFile=asset.empty()?file:Canonical((std::filesystem::u8path(file).parent_path()/std::filesystem::u8path(asset)).u8string());
                const auto& layer=Read(targetFile);
                auto targetPath=reference.prim_path;
                if(!targetPath.is_valid()) {
                    if(!layer.metas().defaultPrim.valid())throw DeadlyImportError("USD reference requires an explicit prim path or defaultPrim: ",targetFile);
                    targetPath=tinyusdz::Path("/"+layer.metas().defaultPrim.str(),"");
                }
                if(!targetPath.is_absolute_path())throw DeadlyImportError("USD reference prim path must be absolute: ",targetFile);
                const Prim* target=nullptr;std::string error;
                if(!layer.find_primspec_at(targetPath,&target,&error) || !target)
                    throw DeadlyImportError("USD referenced prim not found: ",targetFile,targetPath.full_path_name()," ",error);
                auto composed=Compose(*target,targetFile,targetPath.full_path_name(),selections,true,prim.metas().instanceable,prim.metas().active,resolvedSelections);
                if(!prim.metas().instanceable && composed.metas().instanceable && composed.metas().instanceable.value())discardDirectChildren();
                // Descendant overrides require carrying stronger opinions into
                // every referenced child before its arcs are evaluated. Until
                // that contextual composition exists, reject overlap rather
                // than silently ignoring activation/instance child semantics.
                for(const auto& child:prim.children())
                    if(std::any_of(composed.children().begin(),composed.children().end(),[&](const auto& weak){return weak.name()==child.name();}))
                        throw DeadlyImportError("USD overlapping referenced child opinions are not supported; flatten this prim: ",file,primPath,"/",child.name());
                Inherit(prim,composed);unresolved.clear();
                if(prim.metas().active && !prim.metas().active.value())return inactivePrim();
            }
        }
        for(const auto& known:knownSelections)unresolved.erase(known);
        if(!unresolved.empty())throw DeadlyImportError("USD selected variant set not found: ",unresolved.begin()->first," at ",file,primPath);
        // Child reference assets have already been resolved in their own layer;
        // local child overrides can now be processed in this layer's directory.
        for(auto& child:prim.children())child=Compose(child,file,primPath+"/"+child.name(),{},referenced);
        // Expanding instanceable references preserves the authored local matrix;
        // the render converter receives ordinary independent mesh instances.
        return prim;
    }
public:
    explicit StaticUsdComposition(IOSystem& system):io(system){}
    void Load(const std::string& path,tinyusdz::Stage& stage,std::string& warn) {
        const auto file=Canonical(path);const auto& raw=Read(file);Layer composed=raw;
        for(auto& entry:composed.primspecs())entry.second=Compose(entry.second,file,"/"+entry.first);
        std::function<void(Prim&)> expandInstances=[&](Prim& prim){
            prim.metas().instanceable.reset();
            auto& children=prim.children();
            children.erase(std::remove_if(children.begin(),children.end(),[](const auto& child){return child.specifier()!=tinyusdz::Specifier::Def;}),children.end());
            for(auto& child:children)expandInstances(child);
        };
        for(auto entry=composed.primspecs().begin();entry!=composed.primspecs().end();) {
            if(entry->second.specifier()!=tinyusdz::Specifier::Def)entry=composed.primspecs().erase(entry);
            else {expandInstances(entry->second);++entry;}
        }
        std::string error;
        if(!tinyusdz::LayerToStage(composed,&stage,&warnings,&error) || !error.empty())
            throw DeadlyImportError("USD composed stage reconstruction failed: ",error);
        warn+=warnings;
    }
};
}
