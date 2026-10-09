// Self-authored static scene for the bridge regression. No SDK example files
// or vendor model assets are used by this generator.
#define __C4D_64BIT
#define __PC
#include "c4d_file.h"
#include "default_alien_overloads.h"
#include <cstdio>
using namespace cineware;
void GetWriterInfo(Int32& id,String& name){id=0;name="NewPageMergeMDL validation fixture";}
int main(int argc,char** argv) {
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
