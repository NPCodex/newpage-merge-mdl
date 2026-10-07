#include "draco/mesh/triangle_soup_mesh_builder.h"
#include "draco/compression/encode.h"
#include <fstream>
int main(int argc,char** argv){
 if(argc!=2)return 1;draco::TriangleSoupMeshBuilder b;b.Start(1);
 int p=b.AddAttribute(draco::GeometryAttribute::POSITION,3,draco::DT_FLOAT32);
 int n=b.AddAttribute(draco::GeometryAttribute::NORMAL,3,draco::DT_FLOAT32);
 int uv=b.AddAttribute(draco::GeometryAttribute::TEX_COORD,2,draco::DT_FLOAT32);
 float points[3][3]={{-1,0,0},{1,0,0},{0,1,0}},normal[3]={0,0,1},coords[3][2]={{.1f,.2f},{.7f,.3f},{.4f,.9f}};
 b.SetAttributeUniqueId(p,17);b.SetAttributeUniqueId(n,23);b.SetAttributeUniqueId(uv,31);
 b.SetAttributeValuesForFace(p,draco::FaceIndex(0),points[0],points[1],points[2]);
 b.SetAttributeValuesForFace(n,draco::FaceIndex(0),normal,normal,normal);
 b.SetAttributeValuesForFace(uv,draco::FaceIndex(0),coords[0],coords[1],coords[2]);
 auto mesh=b.Finalize();draco::Encoder encoder;encoder.SetSpeedOptions(5,5);draco::EncoderBuffer buffer;
 auto status=encoder.EncodeMeshToBuffer(*mesh,&buffer);if(!status.ok())return 2;
 std::ofstream f(argv[1],std::ios::binary);f.write(buffer.data(),buffer.size());
}
