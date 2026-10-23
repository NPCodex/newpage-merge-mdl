// Self-authored static scene for the bridge regression. No SDK example files
// or vendor model assets are used by this generator.
#define __C4D_64BIT
#define __PC
#include "c4d_file.h"
#include "default_alien_overloads.h"
#include <cstdio>
#include <cstring>
using namespace cineware;
void GetWriterInfo(Int32& id,String& name){id=0;name="NewPageMergeMDL validation fixture";}

bool WriteMaterialFixture(const char* output) {
    BaseDocument* doc=BaseDocument::Alloc();if(!doc)return false;
    BaseObject* parent=BaseObject::Alloc(Onull);parent->SetName("MaterialParent");
    Matrix parentPose;parentPose.off=Vector(200,300,400);parent->SetMl(parentPose);doc->InsertObject(parent,nullptr);
    const char* materialNames[]={"FixtureBlue","FixtureRed","FixtureGreen","UnusedYellow"};
    const Vector colors[]={Vector(.2,.4,.8),Vector(.8,.2,.1),Vector(.1,.8,.2),Vector(.8,.8,.1)};
    Material* materials[4];
    for(int i=0;i<4;++i) {
        auto* material=materials[i]=Material::Alloc();material->SetName(materialNames[i]);
        material->GetDataInstance()->SetBool(MATERIAL_USE_COLOR,true);
        material->GetDataInstance()->SetVector(MATERIAL_COLOR_COLOR,colors[i]);
        material->GetDataInstance()->SetFloat(MATERIAL_COLOR_BRIGHTNESS,1.0);doc->InsertMaterial(material);
    }
    const char* names[]={"SmoothStrip","AuthoredStrip","RestrictedOnly","LastUnrestricted"};
    for(int mode=0;mode<4;++mode) {
        auto* mesh=PolygonObject::Alloc(10,4);mesh->SetName(names[mode]);
        Matrix pose;pose.off=Vector(0,mode*200,0);mesh->SetMl(pose);doc->InsertObject(mesh,parent);
        auto* points=mesh->GetPointW();
        for(int row=0;row<2;++row)for(int x=0;x<5;++x)points[row*5+x]=Vector(x*100,row*100,x>=2?40:0);
        for(int i=0;i<4;++i)mesh->GetPolygonW()[i]=CPolygon(i,i+1,i+6,i+5);
        BaseTag* last=nullptr;
        auto selection=[&](const char* name,int first,int final) {
            auto* tag=static_cast<SelectionTag*>(mesh->MakeTag(Tpolygonselection,last));last=tag;tag->SetName(name);
            for(int i=first;i<=final;++i)tag->GetBaseSelect()->Select(i);
        };
        auto texture=[&](int material,const char* restriction) {
            auto* tag=static_cast<TextureTag*>(mesh->MakeTag(Ttexture,last));last=tag;
            tag->SetMaterial(materials[material]);tag->GetDataInstance()->SetString(TEXTURETAG_RESTRICTION,restriction);
        };
        selection("Middle",1,2);selection("Overlap",2,2);
        if(mode!=2)texture(0,"");
        texture(1,"Middle");texture(2,"Overlap");texture(3,"MissingSelection");
        if(mode==3)texture(0,""); // late unrestricted assignment must override all previous tags
        auto* uv=static_cast<UVWTag*>(mesh->MakeTag(Tuvw,last));last=uv;uv->Resize(4);
        for(int i=0;i<4;++i) {
            UVWStruct value;value.a=Vector(i/4.0,0,0);value.b=Vector((i+1)/4.0,0,0);
            value.c=Vector((i+1)/4.0,1,0);value.d=Vector(i/4.0,1,0);
            UVWTag::Set(uv->GetDataAddressW(),i,value);
        }
        if(mode==1) {
            auto* normal=static_cast<NormalTag*>(mesh->MakeTag(Tnormal,last));normal->Resize(4);
            NormalStruct value;value.a=value.b=value.c=value.d=Vector(0,.6,.8);
            for(int i=0;i<4;++i)NormalTag::Set(normal->GetDataAddressW(),i,value);
        }
    }
    const bool ok=SaveDocument(doc,Filename(output),SAVEDOCUMENTFLAGS_0);
    BaseDocument::Free(doc);return ok;
}

bool WriteRejectedFixture(const char* output, const char* mode) {
    BaseDocument* doc=BaseDocument::Alloc();if(!doc)return false;
    if(std::strcmp(mode,"missing-cache")==0) {
        BaseObject* cube=BaseObject::Alloc(Ocube);cube->SetName("UncachedGenerator");doc->InsertObject(cube,nullptr);
    } else {
        auto* mesh=PolygonObject::Alloc(4,1);mesh->SetName("RejectedQuad");doc->InsertObject(mesh,nullptr);
        auto* points=mesh->GetPointW();points[0]=Vector(0,0,0);points[1]=Vector(100,0,0);
        points[2]=Vector(100,100,0);points[3]=Vector(0,100,0);mesh->GetPolygonW()[0]=CPolygon(0,1,2,3);
        if(std::strcmp(mode,"invalid-index")==0)mesh->GetPolygonW()[0].d=4;
        else if(std::strcmp(mode,"short-uv")==0)static_cast<UVWTag*>(mesh->MakeTag(Tuvw))->Resize(0);
        else if(std::strcmp(mode,"skin")==0)mesh->MakeTag(Tweights);
        else if(std::strcmp(mode,"animated")==0) {
            auto* track=CTrack::Alloc(mesh,DescID(DescLevel(ID_BASEOBJECT_REL_POSITION,DTYPE_VECTOR,0),
                DescLevel(VECTOR_X,DTYPE_REAL,0)),"FixturePosition");
            mesh->InsertTrackSorted(track);auto* curve=track->GetCurve();
            curve->AddKey(BaseTime(0))->SetValue(curve,0);
            curve->AddKey(BaseTime(1))->SetValue(curve,100);
        } else {BaseDocument::Free(doc);return false;}
    }
    const bool ok=SaveDocument(doc,Filename(output),SAVEDOCUMENTFLAGS_0);
    BaseDocument::Free(doc);return ok;
}

int main(int argc,char** argv) {
    if(argc==3 && std::strcmp(argv[2],"materials")==0) {
        const bool ok=WriteMaterialFixture(argv[1]);std::printf("material fixture %s\n",ok?"written":"failed");return ok?0:1;
    }
    if(argc==3) {
        const bool ok=WriteRejectedFixture(argv[1],argv[2]);
        std::printf("rejection fixture %s\n",ok?"written":"failed");return ok?0:1;
    }
    if(argc!=2)return 2;
    BaseDocument* doc=BaseDocument::Alloc();if(!doc)return 1;
    BaseObject* parent=BaseObject::Alloc(Onull);parent->SetName("FixtureParent");
    Matrix pose;pose.off=Vector(200,300,400);parent->SetMl(pose);doc->InsertObject(parent,nullptr);
    PolygonObject* mesh=PolygonObject::Alloc(4,1);mesh->SetName("FixtureQuad");
    Vector* p=mesh->GetPointW();p[0]=Vector(0,0,0);p[1]=Vector(100,0,0);p[2]=Vector(100,100,0);p[3]=Vector(0,100,0);
    mesh->GetPolygonW()[0]=CPolygon(0,1,2,3);doc->InsertObject(mesh,parent);
    Material* material=Material::Alloc();material->SetName("FixtureBlue");
    material->GetDataInstance()->SetBool(MATERIAL_USE_COLOR,true);
    material->GetDataInstance()->SetVector(MATERIAL_COLOR_COLOR,Vector(0.2,0.4,0.8));
    material->GetDataInstance()->SetFloat(MATERIAL_COLOR_BRIGHTNESS,1.0);doc->InsertMaterial(material);
    static_cast<TextureTag*>(mesh->MakeTag(Ttexture))->SetMaterial(material);
    UVWTag* uv=static_cast<UVWTag*>(mesh->MakeTag(Tuvw));uv->Resize(1);
    UVWStruct coordinates;coordinates.a=Vector(0,0,0);coordinates.b=Vector(1,0,0);
    coordinates.c=Vector(1,1,0);coordinates.d=Vector(0,1,0);UVWTag::Set(uv->GetDataAddressW(),0,coordinates);
    const bool ok=SaveDocument(doc,Filename(argv[1]),SAVEDOCUMENTFLAGS_0);
    BaseDocument::Free(doc);std::printf("fixture %s\n",ok?"written":"failed");return ok?0:1;
}
