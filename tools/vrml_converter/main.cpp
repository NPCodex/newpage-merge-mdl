// SPDX-License-Identifier: GPL-3.0-or-later
// Separate process: MeshLab's GPL-2.0-or-later parser is distributed here under
// GPLv3-or-later. No part of it is linked into NewPageMergeMDL.
#include "Parser.h"
#include "Scanner.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <random>
#include <stdexcept>
#include <system_error>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace {
struct TemporaryOutput {
    std::filesystem::path directory, file;
    explicit TemporaryOutput(const std::filesystem::path& destination) {
        std::random_device random;
        for(int attempt=0;attempt<32;++attempt) {
            auto candidate=destination.parent_path()/std::filesystem::u8path(".npmdl-vrml-"+std::to_string(random()));
            std::error_code ec;
            if(std::filesystem::create_directory(candidate,ec)) {
                directory=candidate;file=directory/"converted.x3d";return;
            }
            if(ec && ec!=std::errc::file_exists)throw std::filesystem::filesystem_error("cannot create temporary output directory",candidate,ec);
        }
        throw std::runtime_error("cannot reserve a unique temporary output directory");
    }
    ~TemporaryOutput() {
        std::error_code ignored;
        std::filesystem::remove(file,ignored);
        std::filesystem::remove(directory,ignored);
    }
    void Publish(const std::filesystem::path& destination) {
#ifdef _WIN32
        if(!MoveFileExW(file.c_str(),destination.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
            throw std::system_error(int(GetLastError()),std::system_category(),"cannot replace X3D output");
#else
        std::filesystem::rename(file,destination);
#endif
    }
};

int Convert(int argc,const std::filesystem::path& input,const std::filesystem::path& output) {
    if(argc!=3) {
        std::cerr<<"NewPageVRMLtoX3D (GPLv3+)\nUsage: NewPageVRMLtoX3D input.wrl output.x3d\n";
        return argc==1?0:2;
    }
    try {
        std::error_code equivalentError;
        if(std::filesystem::weakly_canonical(input)==std::filesystem::weakly_canonical(output) ||
           std::filesystem::equivalent(input,output,equivalentError))
            throw std::runtime_error("input and output paths must differ");
        auto size=std::filesystem::file_size(input);
        if(size==0 || size>uintmax_t(std::numeric_limits<int>::max()))throw std::runtime_error("invalid VRML input size");
        std::ifstream file(input,std::ios::binary);
        if(!file)throw std::runtime_error("cannot open VRML input");
        std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(file)),{});
        if(bytes.empty() || bytes.size()>size_t(std::numeric_limits<int>::max()))throw std::runtime_error("invalid VRML input size");
        VrmlTranslator::Scanner scanner(bytes.data(),int(bytes.size()));
        VrmlTranslator::Parser parser(&scanner);parser.Parse();
        if(parser.errors->count)throw std::runtime_error("VRML syntax errors: "+std::to_string(parser.errors->count));
        // Serialize beside the destination, then publish atomically. Syntax,
        // serialization and replacement failures preserve the previous output.
        TemporaryOutput temporary(std::filesystem::absolute(output));
        std::ofstream destination(temporary.file,std::ios::binary|std::ios::trunc);
        if(!destination)throw std::runtime_error("cannot open X3D output");
        parser.doc_.save(destination);destination.flush();
        if(!destination)throw std::runtime_error("cannot write X3D output");
        destination.close();
        if(!destination)throw std::runtime_error("cannot close X3D output");
        temporary.Publish(std::filesystem::absolute(output));
        std::cout<<"Converted VRML to X3D: "<<output.u8string()<<"\n";return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; }
    catch(const char* e) { std::cerr<<e<<"\n"; }
    catch(const wchar_t* e) { std::wcerr<<e<<L"\n"; }
    return 1;
}
}

#ifdef _WIN32
int wmain(int argc,wchar_t** argv) {
    return Convert(argc,argc==3?std::filesystem::path(argv[1]):std::filesystem::path{},
                        argc==3?std::filesystem::path(argv[2]):std::filesystem::path{});
}
#else
int main(int argc,char** argv) {
    return Convert(argc,argc==3?std::filesystem::u8path(argv[1]):std::filesystem::path{},
                        argc==3?std::filesystem::u8path(argv[2]):std::filesystem::path{});
}
#endif
