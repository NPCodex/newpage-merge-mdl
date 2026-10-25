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
    std::set<std::string> loadingLayers;
    std::set<std::string> active;
    size_t expanded=0;
    std::string warnings;

    static std::string Canonical(const std::string& path) {
        std::error_code ec;const auto absolute=std::filesystem::absolute(std::filesystem::u8path(path),ec);
        if(ec)throw DeadlyImportError("USD invalid asset path: ",path);
        const auto canonical=std::filesystem::weakly_canonical(absolute,ec);
        return (ec?absolute.lexically_normal():canonical).u8string();
    }
    // Resolve external assets in the authoring layer before layering changes
    // the traversal context. Internal references still address the final stack.
    static void ResolveAssets(Prim& prim,const std::string& file,size_t depth=0) {
        if(depth>=64)throw DeadlyImportError("USD layer exceeds 64 prim depth at ",file,"/",prim.name());
        auto resolve=[&](tinyusdz::value::AssetPath& asset) {
            const auto authored=asset.GetAssetPath();
            if(!authored.empty())asset=tinyusdz::value::AssetPath(Canonical((std::filesystem::u8path(file).parent_path()/std::filesystem::u8path(authored)).u8string()));
        };
        if(prim.metas().references)for(auto& reference:prim.metas().references.value().second)resolve(reference.asset_path);
        for(auto& entry:prim.props())if(entry.second.is_attribute()) {
            auto& attribute=entry.second.attribute();
            if(auto asset=attribute.get_value<tinyusdz::value::AssetPath>()) {
                resolve(asset.value());attribute.set_value(asset.value());
            } else if(auto assets=attribute.get_value<std::vector<tinyusdz::value::AssetPath>>()) {
                for(auto& asset:assets.value())resolve(asset);
                attribute.set_value(assets.value());
            }
        }
        for(auto& child:prim.children())ResolveAssets(child,file,depth+1);
        for(auto& set:prim.variantSets())for(auto& variant:set.second.variantSet)ResolveAssets(variant.second,file,depth+1);
    }
    static void CheckStaticLayer(const Prim& prim,const std::string& file) {
        const auto& meta=prim.metas();
        if(meta.variantSets || meta.variants || !prim.variantSets().empty())
            throw DeadlyImportError("USD subLayers with variant opinions are not supported; flatten this stack: ",file,"/",prim.name());
        if(meta.payload || meta.inherits || meta.specializes || meta.clips)
            throw DeadlyImportError("USD unsupported payload/inherits/specializes/value-clips in subLayers: ",file,"/",prim.name());
        if(prim.typeName()=="Skeleton" || prim.typeName()=="SkelRoot" || prim.typeName()=="SkelAnimation")
            throw DeadlyImportError("USD skeletal subLayers are not supported; flatten this stack: ",file,"/",prim.name());
        for(const auto& entry:prim.props())if(entry.second.is_attribute() && entry.second.get_attribute().has_timesamples())
            throw DeadlyImportError("USD animated subLayers are not supported; flatten or bake this stack: ",file,"/",prim.name(),".",entry.first);
        for(const auto& child:prim.children())CheckStaticLayer(child,file);
    }
    static void InheritAttribute(tinyusdz::Attribute& strong,const tinyusdz::Attribute& weak) {
        // Declarations without a default do not erase a weaker authored value.
        if(!strong.has_value() && !strong.has_blocked() && !strong.has_connections() && !strong.has_timesamples())
            strong.get_var()=weak.get_var();
        auto& s=strong.metas();const auto& w=weak.metas();
        auto fill=[](auto& dst,const auto& src){if(!dst)dst=src;};
        fill(s.interpolation,w.interpolation);fill(s.elementSize,w.elementSize);fill(s.hidden,w.hidden);
        fill(s.comment,w.comment);fill(s.weight,w.weight);fill(s.connectability,w.connectability);
        fill(s.outputName,w.outputName);fill(s.renderType,w.renderType);fill(s.displayName,w.displayName);
        fill(s.bindMaterialAs,w.bindMaterialAs);
        // Dictionary metadata needs field-wise composition, outside this bounded
        // static value merger. Never discard a weaker dictionary silently.
        if((s.customData && w.customData) || (s.sdrMetadata && w.sdrMetadata))
            throw DeadlyImportError("USD layered attribute dictionary metadata requires flattening");
        fill(s.customData,w.customData);fill(s.sdrMetadata,w.sdrMetadata);
        for(const auto& entry:w.meta)s.meta.emplace(entry);
        if(s.stringData.empty())s.stringData=w.stringData;
    }
    static void InheritLayer(Prim& strong,const Prim& weak) {
        if(strong.specifier()==tinyusdz::Specifier::Over)strong.specifier()=weak.specifier();
        if(strong.typeName().empty() || strong.typeName()=="Model")strong.typeName()=weak.typeName();
        auto weakMeta=weak.metas();
        if(strong.metas().apiSchemas && weakMeta.apiSchemas)
            throw DeadlyImportError("USD layered API schema lists require flattening: ",strong.name());
        if(strong.metas().references && weakMeta.references) {
            using Qual=tinyusdz::ListEditQual;
            const auto& refs=strong.metas().references.value();
            if(refs.first!=Qual::ResetToExplicit && refs.first!=Qual::Prepend && refs.first!=Qual::Append && refs.first!=Qual::Add)
                throw DeadlyImportError("USD unsupported layered reference list edit: ",strong.name());
            if(refs.first==Qual::ResetToExplicit)weakMeta.references.reset();
            else if(!refs.second.empty() && !weakMeta.references.value().second.empty())
                throw DeadlyImportError("USD multiple layered reference list opinions require flattening: ",strong.name());
            else if(refs.second.empty())strong.metas().references.reset();
        }
        strong.metas().update_from(weakMeta,false);
        // tinyusdz's dictionary updater merges two authored dictionaries, but
        // omits a weak-only dictionary when override_authored is false.
        if(!strong.metas().assetInfo)strong.metas().assetInfo=weakMeta.assetInfo;
        if(!strong.metas().customData)strong.metas().customData=weakMeta.customData;
        if(!strong.metas().sdrMetadata)strong.metas().sdrMetadata=weakMeta.sdrMetadata;
        for(const auto& property:weak.props()) {
            auto inserted=strong.props().emplace(property);
            if(inserted.second)continue;
            auto& current=inserted.first->second;
            if(!current.is_attribute() || !property.second.is_attribute() ||
               current.attribute().has_connections() || property.second.get_attribute().has_connections() ||
               current.value_type_name()!=property.second.value_type_name())
                throw DeadlyImportError("USD layered relationship/connection/type overrides require flattening: ",strong.name(),".",property.first);
            InheritAttribute(current.attribute(),property.second.get_attribute());
            if(current.attribute().has_value() || current.attribute().has_blocked())
                current.set_property_type(tinyusdz::Property::Type::Attrib);
        }
        for(const auto& child:weak.children()) {
            auto found=std::find_if(strong.children().begin(),strong.children().end(),[&](const auto& current){return current.name()==child.name();});
            if(found==strong.children().end())strong.children().push_back(child);else InheritLayer(*found,child);
        }
    }
    const Layer& Read(const std::string& path) {
        auto found=layers.find(path);if(found!=layers.end())return found->second;
        if(loadingLayers.count(path))throw DeadlyImportError("USD cyclic subLayers at ",path);
        if(loadingLayers.size()>=64)throw DeadlyImportError("USD subLayers exceed 64 layer depth at ",path);
        if(layers.size()+loadingLayers.size()>=128)throw DeadlyImportError("USD composition exceeds 128 source layers");
        loadingLayers.insert(path);
        struct LeaveLayer {std::set<std::string>& active;std::string path;~LeaveLayer(){active.erase(path);}} leave{loadingLayers,path};
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
        for(auto& entry:layer.primspecs())ResolveAssets(entry.second,path);
        // Root opinions are strongest, followed by subLayers in authored order.
        // Stage metadata (including defaultPrim and upAxis) belongs to the root
        // layer and does not inherit from a sublayer, matching OpenUSD.
        if(!layer.metas().subLayers.empty()) {
            for(const auto& entry:layer.primspecs())CheckStaticLayer(entry.second,path);
            for(const auto& sub:layer.metas().subLayers) {
                if(sub.layerOffset._offset!=0 || sub.layerOffset._scale!=1)
                    throw DeadlyImportError("USD subLayer time offsets are not supported: ",path);
                const auto asset=sub.assetPath.GetAssetPath();
                if(asset.empty())throw DeadlyImportError("USD empty subLayer asset path: ",path);
                const auto file=Canonical((std::filesystem::u8path(path).parent_path()/std::filesystem::u8path(asset)).u8string());
                const auto& weaker=Read(file);
                for(const auto& entry:weaker.primspecs()) {
                    CheckStaticLayer(entry.second,file);
                    auto inserted=layer.primspecs().emplace(entry);
                    if(!inserted.second)InheritLayer(inserted.first->second,entry.second);
                }
            }
            layer.metas().subLayers.clear();
        }
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
