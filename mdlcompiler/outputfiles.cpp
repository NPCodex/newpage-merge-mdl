#include "outputfiles.h"
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <io.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace {
namespace fs=std::filesystem;
constexpr uint64_t kBasis=14695981039346656037ULL;
struct Digest { uint64_t size=0,hash=kBasis; };
bool operator==(const Digest& a,const Digest& b){return a.size==b.size&&a.hash==b.hash;}
Digest Bytes(const void* data,size_t size) {
    Digest d;d.size=size;for(size_t i=0;i<size;++i){d.hash^=static_cast<const unsigned char*>(data)[i];d.hash*=1099511628211ULL;}return d;
}
bool Exists(const fs::path& p) {
    std::error_code ec;auto status=fs::symlink_status(p,ec);
    if(ec&&ec!=std::errc::no_such_file_or_directory)throw std::runtime_error("cannot inspect "+p.string()+": "+ec.message());
    if(!fs::exists(status))return false;
    if(!fs::is_regular_file(status))throw std::runtime_error("output is not a regular file: "+p.string());
    return true;
}
Digest FileDigest(const fs::path& p) {
    std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("cannot read output: "+p.string());
    Digest d;char buffer[65536];while(f){f.read(buffer,sizeof(buffer));auto n=f.gcount();d.size+=uint64_t(n);
        for(std::streamsize i=0;i<n;++i){d.hash^=static_cast<unsigned char>(buffer[i]);d.hash*=1099511628211ULL;}}
    if(!f.eof())throw std::runtime_error("cannot finish reading output: "+p.string());return d;
}
std::string Key(fs::path p) {
    auto s=p.generic_string();
#ifdef _WIN32
    for(char& c:s)c=char(std::tolower(static_cast<unsigned char>(c)));
#endif
    return s;
}
// Journal paths stay under the caller's output root. Reject symlink/reparse
// components rather than letting an old journal redirect a recovery elsewhere.
fs::path Resolve(const fs::path& root,const fs::path& relative) {
    if(relative.empty()||relative.is_absolute()||relative.has_root_name())throw std::runtime_error("unsafe output journal path");
    fs::path at=root;
    for(const auto& part:relative) {
        if(part==".."||part==".")throw std::runtime_error("unsafe output journal path");
        at/=part;std::error_code ec;auto status=fs::symlink_status(at,ec);
        if(ec&&ec!=std::errc::no_such_file_or_directory)throw std::runtime_error("cannot inspect output path: "+ec.message());
        if(fs::is_symlink(status))throw std::runtime_error("output path contains a symbolic link: "+at.string());
#ifdef _WIN32
        const auto attrs=GetFileAttributesW(at.c_str());
        if(attrs!=INVALID_FILE_ATTRIBUTES&&(attrs&FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("output path contains a reparse point: "+at.string());
#endif
    }
    return at;
}
fs::path Relative(const fs::path& root,const fs::path& p) {
    const auto absolute=fs::absolute(p).lexically_normal();
    auto relative=absolute.lexically_relative(root);
#ifdef _WIN32
    // canonical(root) expands 8.3 names and restores on-disk casing under
    // MSVC. The caller's path may still contain RUNNER~1 or different case.
    // Find the first prefix naming the same directory, then validate every
    // remaining component. Canonicalizing the whole input first would hide a
    // junction/symlink below the output root, including one back to root.
    fs::path prefix=absolute.root_path(),tail=absolute.relative_path();
    bool matched=false;
    for(auto it=tail.begin();;){
        std::error_code ec;
        if(fs::equivalent(prefix,root,ec)&&!ec){
            relative.clear();for(;it!=tail.end();++it)relative/=*it;
            matched=true;break;
        }
        if(it==tail.end())break;
        prefix/=*it++;
    }
    if(!matched)throw std::runtime_error("unsafe output journal path");
    const auto checked=Resolve(root,relative);
    // Only after the reparse checks, normalize existing child aliases too,
    // so short and long spellings take the same per-output process lock.
    relative=fs::weakly_canonical(checked).lexically_relative(root);
#endif
    Resolve(root,relative);return relative;
}
void SyncDirectory(const fs::path& path) {
#ifndef _WIN32
    int fd=open(path.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if(fd<0)throw std::runtime_error("cannot open output directory for sync: "+path.string());
    int result=fsync(fd);close(fd);if(result)throw std::runtime_error("cannot sync output directory: "+path.string());
#else
    (void)path; // Rename uses MOVEFILE_WRITE_THROUGH; files use FlushFileBuffers.
#endif
}
void WriteFile(const fs::path& path,const void* data,size_t size) {
    FILE* f=nullptr;
#ifdef _WIN32
    _wfopen_s(&f,path.c_str(),L"wbx");
#else
    f=std::fopen(path.c_str(),"wbx");
#endif
    if(!f)throw std::runtime_error("cannot stage output: "+path.string());
    bool ok=std::fwrite(data,1,size,f)==size&&std::fflush(f)==0;
#ifdef _WIN32
    if(ok)ok=FlushFileBuffers(reinterpret_cast<HANDLE>(_get_osfhandle(_fileno(f))))!=0;
#else
    if(ok)ok=fsync(fileno(f))==0;
#endif
    if(std::fclose(f))ok=false;
    if(!ok)throw std::runtime_error("incomplete output write: "+path.string());
    SyncDirectory(path.parent_path());
}
void Rename(const fs::path& from,const fs::path& to) {
#ifdef _WIN32
    if(!MoveFileExW(from.c_str(),to.c_str(),MOVEFILE_WRITE_THROUGH))throw std::runtime_error("cannot rename output "+from.string()+" to "+to.string()+" (Windows error "+std::to_string(GetLastError())+")");
#else
    if(fs::exists(to))throw std::runtime_error("output rename destination already exists: "+to.string());
    fs::rename(from,to);SyncDirectory(from.parent_path());if(from.parent_path()!=to.parent_path())SyncDirectory(to.parent_path());
#endif
}
void Remove(const fs::path& p){if(Exists(p)){fs::remove(p);SyncDirectory(p.parent_path());}}
struct Lock {
#ifdef _WIN32
    HANDLE handle=INVALID_HANDLE_VALUE;
    explicit Lock(const fs::path& p){handle=CreateFileW(p.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_HIDDEN,nullptr);
        if(handle==INVALID_HANDLE_VALUE)throw std::runtime_error("output is locked by another compiler: "+p.string());}
    ~Lock(){if(handle!=INVALID_HANDLE_VALUE)CloseHandle(handle);}
#else
    int fd=-1;
    explicit Lock(const fs::path& p){fd=open(p.c_str(),O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
        if(fd<0)throw std::runtime_error("cannot open output lock: "+p.string());
        if(flock(fd,LOCK_EX|LOCK_NB)){close(fd);fd=-1;throw std::runtime_error("output is locked by another compiler: "+p.string());}}
    ~Lock(){if(fd>=0){flock(fd,LOCK_UN);close(fd);}}
#endif
};
struct Entry {
    fs::path relative,path,stage,backup;
    bool hadOld=false;
    Digest oldDigest,newDigest;
};
struct Journal {
    fs::path root,path,commit;
    std::string nonce;
    std::vector<Entry> entries;
};
Journal Location(const fs::path& model,const fs::path& outputRoot) {
    Journal j;fs::create_directories(outputRoot);j.root=fs::canonical(outputRoot);
    auto relative=Relative(j.root,model);j.path=Resolve(j.root,fs::path(relative.string()+".npmdl-journal"));j.commit=j.path.string()+".commit";return j;
}
void Derive(Journal& j,Entry& e,size_t i) {
    e.path=Resolve(j.root,e.relative);const auto suffix=".npmdl-"+j.nonce+"-"+std::to_string(i);
    e.stage=e.path.string()+suffix+".stage";e.backup=e.path.string()+suffix+".backup";
    Resolve(j.root,Relative(j.root,e.stage));Resolve(j.root,Relative(j.root,e.backup));
}
void Read(Journal& j) {
    if(!Exists(j.path))return;
    if(fs::file_size(j.path)>1024*1024)throw std::runtime_error("output recovery journal exceeds 1 MiB");
    std::ifstream f(j.path,std::ios::binary);std::string magic;size_t count=0;
    if(!(f>>magic>>j.nonce>>count)||magic!="NPMDL_TXN_1"||j.nonce.empty()||j.nonce.find_first_not_of("0123456789-")!=std::string::npos||count==0||count>64)
        throw std::runtime_error("invalid output recovery journal: "+j.path.string());
    std::set<std::string> seen;
    for(size_t i=0;i<count;++i) {
        Entry e;std::string relative;int had=0;
        if(!(f>>std::quoted(relative)>>had>>e.oldDigest.size>>e.oldDigest.hash>>e.newDigest.size>>e.newDigest.hash)||(had!=0&&had!=1))throw std::runtime_error("truncated output recovery journal: "+j.path.string());
        e.relative=fs::u8path(relative);e.hadOld=had!=0;Derive(j,e,i);
        if(!seen.insert(Key(e.path)).second)throw std::runtime_error("duplicate output recovery path");
        const auto ext=e.path.extension().string();if(ext!=".mdl"&&ext!=".vvd"&&ext!=".vtx"&&ext!=".phy"&&ext!=".ani")throw std::runtime_error("unsupported output recovery extension");
        j.entries.push_back(std::move(e));
    }
    f>>std::ws;if(!f.eof())throw std::runtime_error("unexpected output recovery journal data");
    if(std::none_of(j.entries.begin(),j.entries.end(),[&](const Entry& e){return Key(e.path.string()+".npmdl-journal")==Key(j.path);}))throw std::runtime_error("journal does not own its primary output");
}
void Write(const Journal& j) {
    std::ostringstream text;text<<"NPMDL_TXN_1 "<<j.nonce<<" "<<j.entries.size()<<"\n";
    for(const auto& e:j.entries)text<<std::quoted(e.relative.generic_u8string())<<" "<<e.hadOld<<" "<<e.oldDigest.size<<" "<<e.oldDigest.hash<<" "<<e.newDigest.size<<" "<<e.newDigest.hash<<"\n";
    auto s=text.str();WriteFile(j.path,s.data(),s.size());
}
std::vector<std::unique_ptr<Lock>> Locks(const Journal& old,const std::vector<PendingOutput>& outputs={}) {
    std::set<std::string> names;
    for(const auto& e:old.entries)names.insert(Key(e.relative));
    for(const auto& e:outputs)names.insert(Key(Relative(old.root,e.path)));
    // The primary journal serializes compiles whose companion sets differ.
    // Shared .phy/.ani outputs additionally use their own process locks.
    names.insert(Key(Relative(old.root,old.path)));
    auto directory=Resolve(old.root,".npmdl_locks");fs::create_directories(directory);
    std::vector<std::unique_ptr<Lock>> locks;
    for(const auto& name:names){auto d=Bytes(name.data(),name.size());std::ostringstream filename;filename<<std::hex<<d.hash<<".lock";
        auto path=Resolve(old.root,fs::path(".npmdl_locks")/filename.str());locks.push_back(std::make_unique<Lock>(path));}
    return locks;
}
void Match(const fs::path& p,const Digest& digest) {
    if(!Exists(p)||!(FileDigest(p)==digest))throw std::runtime_error("output changed since transaction; recovery retained for review: "+p.string());
}
// Idempotent: interruption during recovery can run through the same journal
// again. Never delete a destination whose contents differ from the transaction.
void Recover(Journal& j) {
    if(j.entries.empty())return;
    const bool committed=Exists(j.commit);
    if(committed) {
        std::ifstream marker(j.commit);std::string value;marker>>value;
        if(value!=j.nonce)throw std::runtime_error("invalid output commit marker");
        for(const auto& e:j.entries)Match(e.path,e.newDigest);
    }else {
        // Validate the whole set before touching any member.
        for(const auto& e:j.entries) {
            const bool backup=Exists(e.backup),target=Exists(e.path);
            if(backup){if(!e.hadOld)throw std::runtime_error("unexpected output recovery backup");Match(e.backup,e.oldDigest);if(target)Match(e.path,e.newDigest);}
            else if(e.hadOld)Match(e.path,e.oldDigest);
            else if(target)Match(e.path,e.newDigest);
            Exists(e.stage);
        }
        for(auto it=j.entries.rbegin();it!=j.entries.rend();++it) {
            const auto& e=*it;
            if(Exists(e.backup)){Remove(e.path);Rename(e.backup,e.path);}
            else if(!e.hadOld)Remove(e.path);
        }
    }
    for(const auto& e:j.entries){Remove(e.stage);if(Exists(e.backup)){Match(e.backup,e.oldDigest);Remove(e.backup);}}
    // Removing journal before marker leaves only an inert marker if killed
    // between these two operations; the next writer discards it under its lock.
    Remove(j.path);Remove(j.commit);
    std::printf("%s interrupted output transaction (%zu files)\n",committed?"Finalized":"Recovered",j.entries.size());
}
#ifdef NPMDL_OUTPUT_TESTING
void Checkpoint(const char* name) {
    if(const char* selected=std::getenv("NPMDL_TEST_CRASH"))if(std::string(selected)==name)std::_Exit(86);
}
#else
void Checkpoint(const char*){}
#endif
}

bool RecoverOutputFiles(const fs::path& model,const fs::path& root,std::string* error) {
    try {
        auto journal=Location(model,root);if(!Exists(journal.path)&&!Exists(journal.commit))return true;
        Read(journal);auto locks=Locks(journal);Recover(journal);if(journal.entries.empty())Remove(journal.commit);return true;
    }catch(const std::exception& e){if(error)*error=e.what();return false;}
}

bool SaveOutputSet(const std::vector<PendingOutput>& outputs,const fs::path& root,std::string* error) {
    Journal journal;bool recorded=false,committed=false;
    std::vector<std::unique_ptr<Lock>> locks;
    try {
        if(outputs.empty())return true;
        const auto primary=std::find_if(outputs.begin(),outputs.end(),[](const PendingOutput& p){return p.path.extension()==".mdl";});
        if(primary==outputs.end())throw std::runtime_error("output set needs a primary MDL");
        journal=Location(primary->path,root);Read(journal);locks=Locks(journal,outputs);Recover(journal);Remove(journal.commit);
        journal.entries.clear();journal.nonce=std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        std::set<std::string> paths;
        for(const auto& output:outputs) {
            Entry e;e.relative=Relative(journal.root,output.path);Derive(journal,e,journal.entries.size());
            if(!paths.insert(Key(e.path)).second)throw std::runtime_error("duplicate output path: "+e.path.string());
            fs::create_directories(e.path.parent_path());e.hadOld=Exists(e.path);
            if(e.hadOld) {
                auto permissions=fs::status(e.path).permissions();const auto writes=fs::perms::owner_write|fs::perms::group_write|fs::perms::others_write;
                if((permissions&writes)==fs::perms::none)throw std::runtime_error("output is read-only: "+e.path.string());
                e.oldDigest=FileDigest(e.path);
            }
            e.newDigest=Bytes(output.data,output.size);
            if(Exists(e.stage)||Exists(e.backup))throw std::runtime_error("output temporary path is already occupied");
            journal.entries.push_back(std::move(e));
        }
        // Publish complete intent before staging or renaming originals. A torn
        // initial journal leaves the old set untouched and requires review.
        Write(journal);recorded=true;Checkpoint("journal");
        for(size_t i=0;i<outputs.size();++i){WriteFile(journal.entries[i].stage,outputs[i].data,outputs[i].size);Checkpoint("stage");}
        for(const auto& e:journal.entries)if(e.hadOld){Rename(e.path,e.backup);Checkpoint("backup");}
        // Publish MDL last, after all companion files.
        for(int pass=0;pass<2;++pass)for(const auto& e:journal.entries)if((e.path.extension()==".mdl")==bool(pass)){
            Rename(e.stage,e.path);Checkpoint(pass?"mdl":"install");}
        WriteFile(journal.commit,journal.nonce.data(),journal.nonce.size());committed=true;Checkpoint("commit");
        for(const auto& e:journal.entries)Remove(e.backup);
        Remove(journal.path);Remove(journal.commit);return true;
    }catch(const std::exception& e) {
        std::string message=e.what();
        if(recorded&&!committed){try{Recover(journal);}catch(const std::exception& recovery){message+="; recovery retained: "+std::string(recovery.what());}}
        if(committed){std::fprintf(stderr,"warning: output committed; cleanup will retry next compile: %s\n",message.c_str());return true;}
        if(error)*error="output transaction: "+message;return false;
    }
}
