// Standalone fault-injection build. NPMDL_OUTPUT_TESTING is absent from the
// production compiler; only this executable can exit at a write checkpoint.
#define NPMDL_OUTPUT_TESTING
#include "../mdlcompiler/outputfiles.cpp"
#include <thread>

int main(int argc,char** argv) {
    if(argc<3)return 2;
    fs::path root=fs::absolute(argv[1]);std::string mode=argv[2],error;
    fs::create_directories(root);
    const auto output=argc>3?root/fs::path(argv[3]):root;
    if(mode=="recover") {
        if(RecoverOutputFiles(output/"fixture.mdl",root,&error))return 0;
    }else if(mode=="hold") {
        auto journal=Location(output/"fixture.mdl",root);Read(journal);auto locks=Locks(journal);
        std::puts("LOCKED");std::fflush(stdout);std::this_thread::sleep_for(std::chrono::seconds(20));return 0;
    }else {
        std::string mdl=mode+"-model",vvd=mode+"-vertices",vtx=mode+"-indices",phy=mode+"-physics";
        std::vector<PendingOutput> outputs{{output/"fixture.mdl",mdl.data(),mdl.size()},
            {output/"fixture.vvd",vvd.data(),vvd.size()},{output/"fixture.dx90.vtx",vtx.data(),vtx.size()},
            {output/"collision/other.phy",phy.data(),phy.size()}};
        if(SaveOutputSet(outputs,root,&error))return 0;
    }
    std::fprintf(stderr,"%s\n",error.c_str());return 1;
}
