#include "resources.h"
#include <fstream>
#include <iostream>
#include <iterator>
int main(int argc,char** argv) {
    try {
    if(argc!=4)return 2;
    std::string error;
    if(!pulse::resources::Initialize(argv[1],"",&error)){std::cerr<<error;return 3;}
    if(std::string(argv[2])=="content")pulse::resources::EnableContentSearch();
    const auto path=pulse::resources::Find(argv[3]);
    if(path.empty())return 4;
    std::ifstream file(path,std::ios::binary);
    std::cout<<std::string(std::istreambuf_iterator<char>(file),{});
    return file.bad()?5:0;
    } catch(const std::exception& error) { std::cerr<<error.what();return 6; }
}
