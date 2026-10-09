#include "resources.h"
#include "pathcompat.h"
#include "dependencies.h"
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif
namespace pulse::resources {
namespace {
namespace fs=std::filesystem;
std::string Lower(std::string s){for(char& c:s)c=char(std::tolower(static_cast<unsigned char>(c)));return s;}
struct KV {std::string key,value;std::vector<KV> children;};
std::vector<std::string> Tokens(const std::string& text) {
 std::vector<std::string> out;size_t i=0;
 while(i<text.size()) {
  if(std::isspace(static_cast<unsigned char>(text[i]))){++i;continue;}
  if(text.compare(i,2,"//")==0){while(i<text.size()&&text[i]!='\n')++i;continue;}
  if(text[i]=='{'||text[i]=='}'){out.push_back(text.substr(i++,1));continue;}
  std::string s;
  if(text[i]=='"'){++i;while(i<text.size()&&text[i]!='"'){
   if(text[i]=='\\'&&i+1<text.size()&&(text[i+1]=='\\'||text[i+1]=='"'))++i;
   s+=text[i++];}if(i==text.size())throw std::runtime_error("unterminated KeyValues string");++i;
  }else{while(i<text.size()&&!std::isspace(static_cast<unsigned char>(text[i]))&&text[i]!='{'&&text[i]!='}')s+=text[i++];}
  out.push_back(std::move(s));
 }return out;
}
std::vector<KV> Parse(const std::vector<std::string>& ts,size_t& i,bool nested=false,int depth=0) {
 if(depth>64)throw std::runtime_error("KeyValues nesting limit exceeded");std::vector<KV> out;
 while(i<ts.size()&&ts[i]!="}") {
  KV n;n.key=ts[i++];if(i==ts.size())throw std::runtime_error("missing KeyValues value");
  if(ts[i]=="{"){++i;n.children=Parse(ts,i,true,depth+1);}else n.value=ts[i++];
  bool enabled=true;
  if(i<ts.size()&&!ts[i].empty()&&ts[i][0]=='['){const auto condition=Lower(ts[i++]);
#ifdef _WIN32
   enabled=condition!="[$linux]"&&condition!="[$posix]";
#else
   enabled=condition!="[$win32]"&&condition!="[$windows]";
#endif
  }if(enabled)out.push_back(std::move(n));
 }if(nested){if(i==ts.size())throw std::runtime_error("missing KeyValues closing brace");++i;}return out;
}
std::vector<KV> ReadKV(const fs::path& path) {
 std::ifstream f(path,std::ios::binary);if(!f)return {};std::ostringstream s;s<<f.rdbuf();
 auto text=s.str();if(text.size()>=3&&uint8_t(text[0])==0xef&&uint8_t(text[1])==0xbb&&uint8_t(text[2])==0xbf)text.erase(0,3);
 auto ts=Tokens(text);size_t i=0;auto out=Parse(ts,i);if(i!=ts.size())throw std::runtime_error("unexpected KeyValues closing brace");
 dependencies::Note(path.string());return out;
}
const KV* Child(const std::vector<KV>& nodes,const std::string& name){for(const auto& n:nodes)if(Lower(n.key)==Lower(name))return &n;return nullptr;}
struct Entry {uint16_t archive=0;uint32_t offset=0,length=0;std::vector<char> preload;};
struct Mount {fs::path path;bool loaded=false;uint64_t dataStart=0;std::map<std::string,Entry> entries;};
struct State {
 std::vector<Mount> mounts,contentMounts;bool contentSearch=false,csgoTarget=false;int targetVtx=-1;fs::path cache,gameDirectory;
 ~State(){if(!cache.empty()){std::error_code ec;auto parent=fs::temp_directory_path(ec).lexically_normal();
  if(!ec&&cache.parent_path()==parent&&cache.filename().string().rfind("newpage-mount-",0)==0)fs::remove_all(cache,ec);}}
} state;
uint16_t U16(const std::vector<char>& b,size_t& i){if(i+2>b.size())throw std::runtime_error("truncated VPK entry");uint16_t x=uint8_t(b[i])|(uint16_t(uint8_t(b[i+1]))<<8);i+=2;return x;}
uint32_t U32(const std::vector<char>& b,size_t& i){uint32_t lo=U16(b,i),hi=U16(b,i);return lo|(hi<<16);}
std::string CString(const std::vector<char>& b,size_t& i){size_t start=i;while(i<b.size()&&b[i])++i;if(i==b.size())throw std::runtime_error("truncated VPK string");std::string s(b.data()+start,i-start);++i;return s;}
bool SafeRelative(const fs::path& p){if(p.empty()||p.is_absolute()||p.has_root_name())return false;for(const auto& part:p)if(part=="..")return false;return true;}
std::string ArchivePath(std::string name) {
 // VPK keys are byte strings, not host filesystem paths. Official L4D2
 // archives contain Latin-1 names alongside ASCII. Converting every entry to
 // a Windows wide path would reject the whole mount on an unrelated name.
 std::replace(name.begin(),name.end(),'\\','/');
 if(name.empty()||name.front()=='/'||name.find(':')!=std::string::npos)
  throw std::runtime_error("unsafe VPK path");
 std::vector<std::string> parts;size_t start=0;
 while(start<name.size()) {
  auto end=name.find('/',start);if(end==std::string::npos)end=name.size();
  auto part=name.substr(start,end-start);start=end+1;
  if(part.empty()||part==".")continue;
  if(part==".."){if(parts.empty())throw std::runtime_error("unsafe VPK path");parts.pop_back();}
  else parts.push_back(std::move(part));
 }
 if(parts.empty())throw std::runtime_error("unsafe VPK path");
 std::string result;for(const auto& part:parts){if(!result.empty())result+='/';result+=part;}
 return Lower(std::move(result));
}
void Index(Mount& m) {
 if(m.loaded)return;m.loaded=true;std::ifstream f(m.path,std::ios::binary);
 std::vector<char> header(12);f.read(header.data(),12);size_t h=0;
 if(!f||U32(header,h)!=0x55aa1234)throw std::runtime_error("invalid VPK signature: "+m.path.string());
 uint32_t version=U32(header,h),size=U32(header,h);
 if(version!=1&&version!=2)throw std::runtime_error("unsupported VPK version");
 if(size>256*1024*1024)throw std::runtime_error("VPK directory exceeds 256 MiB");
 m.dataStart=(version==1?12:28)+uint64_t(size);f.seekg(version==1?12:28);
 std::vector<char> tree(size);f.read(tree.data(),size);if(!f)throw std::runtime_error("truncated VPK directory");size_t i=0;
 for(std::string ext=CString(tree,i);!ext.empty();ext=CString(tree,i))
  for(std::string dir=CString(tree,i);!dir.empty();dir=CString(tree,i))
   for(std::string name=CString(tree,i);!name.empty();name=CString(tree,i)) {
    U32(tree,i);uint16_t preload=U16(tree,i);Entry e;e.archive=U16(tree,i);e.offset=U32(tree,i);e.length=U32(tree,i);
    if(U16(tree,i)!=0xffff||preload>tree.size()-i)throw std::runtime_error("invalid VPK entry");
    e.preload.assign(tree.begin()+i,tree.begin()+i+preload);i+=preload;
    auto key=ArchivePath((dir==" "?"":dir+"/")+name+(ext==" "?"":"."+ext));
    m.entries.emplace(std::move(key),std::move(e));
   }
 dependencies::Note(m.path.string());
}
bool WildcardMatch(const std::string& pattern,const std::string& name) {
 size_t p=0,n=0,star=std::string::npos,retry=0;
 while(n<name.size()) {
  if(p<pattern.size()&&(pattern[p]=='?'||pattern[p]==name[n])){++p;++n;}
  else if(p<pattern.size()&&pattern[p]=='*'){star=p++;retry=n;}
  else if(star!=std::string::npos){p=star+1;n=++retry;}
  else return false;
 }
 while(p<pattern.size()&&pattern[p]=='*')++p;
 return p==pattern.size();
}
bool ArchiveChunk(const fs::path& p) {
 const auto name=p.stem().string();
 return name.size()>4&&name[name.size()-4]=='_'&&name.substr(name.size()-3).find_first_not_of("0123456789")==std::string::npos;
}
void Add(fs::path p,bool content=false) {
 p=p.lexically_normal();std::error_code ec;
 fs::path prefix;
 for(auto part=p.begin();part!=p.end();++part) {
  const auto pattern=part->string();
  if(pattern.find_first_of("*?")==std::string::npos){prefix/=*part;continue;}
  fs::path suffix;for(auto tail=std::next(part);tail!=p.end();++tail)suffix/=*tail;
  std::vector<fs::path> matches;
  for(fs::directory_iterator it(prefix,ec),end;!ec&&it!=end;it.increment(ec))
   if(WildcardMatch(Lower(pattern),Lower(it->path().filename().string())))matches.push_back(it->path());
  std::sort(matches.begin(),matches.end());for(const auto& x:matches)Add(suffix.empty()?x:x/suffix,content);return;
 }
 if(!fs::exists(p,ec)&&Lower(p.extension().string())==".vpk"){auto s=p.string();s.resize(s.size()-4);p=FilePath(s+"_dir.vpk");}
 if(!fs::exists(p,ec))return;
 if(!fs::is_directory(p,ec)&&(Lower(p.extension().string())!=".vpk"||ArchiveChunk(p)))return;
 auto& mounts=content?state.contentMounts:state.mounts;
 for(const auto& m:mounts)if(m.path==p)return;mounts.push_back({p});
 if(fs::is_directory(p,ec)){
  std::vector<fs::path> archives;for(fs::directory_iterator it(p,ec),end;!ec&&it!=end;it.increment(ec))if(Lower(it->path().extension().string())==".vpk"){
   if(!ArchiveChunk(it->path()))archives.push_back(it->path());}
  std::sort(archives.begin(),archives.end());for(const auto& archive:archives)Add(archive,content);
 }
}
fs::path SteamRoot(const std::string& overridePath) {
 if(!overridePath.empty())return fs::absolute(FilePath(overridePath));
 if(const char* p=std::getenv("NEWPAGE_STEAM_PATH"))return fs::absolute(FilePath(p));
#ifdef _WIN32
 wchar_t value[32768];DWORD bytes=sizeof(value);
 if(RegGetValueW(HKEY_CURRENT_USER,L"Software\\Valve\\Steam",L"SteamPath",RRF_RT_REG_SZ,nullptr,value,&bytes)==ERROR_SUCCESS)return fs::path(value);
#else
 if(const char* p=std::getenv("HOME")){auto root=fs::path(p)/".steam/steam";if(fs::exists(root))return root;return fs::path(p)/".local/share/Steam";}
#endif
 return {};
}
fs::path AppDirectory(const fs::path& steam,const std::string& id) {
 if(steam.empty()||id.empty()||id.find_first_not_of("0123456789")!=std::string::npos)return {};
 std::vector<fs::path> libs{steam};auto folders=ReadKV(steam/"steamapps/libraryfolders.vdf");
 if(auto root=Child(folders,"libraryfolders"))for(const auto& n:root->children){if(auto p=Child(n.children,"path"))libs.push_back(FilePath(p->value));else if(!n.value.empty()&&n.key.find_first_not_of("0123456789")==std::string::npos)libs.push_back(FilePath(n.value));}
 for(const auto& lib:libs){auto manifest=ReadKV(lib/"steamapps"/("appmanifest_"+id+".acf"));auto app=Child(manifest,"appstate");if(!app)continue;
  auto install=Child(app->children,"installdir");if(install){auto relative=FilePath(install->value);if(!SafeRelative(relative))throw std::runtime_error("unsafe Steam install directory");return lib/"steamapps/common"/relative;}}
 return {};
}
}
bool LaunchDefaults(const std::string& gameDirectory,const std::string& script,
                    std::vector<std::string>& arguments,std::string* err) {
 try {
  if(gameDirectory.empty()||script.empty())return true;
  const auto game=fs::absolute(FilePath(gameDirectory));
  const auto info=ReadKV(game/"gameinfo.txt");
  const auto root=Child(info,"gameinfo");
  const auto tools=root?Child(root->children,"tools"):nullptr;
  const auto defaults=tools?Child(tools->children,"studiomdl"):nullptr;
  // This is command-line tokenization, not a second KeyValues parse: braces,
  // // and single backslashes can be ordinary option values. Quoted paths may
  // contain whitespace; Windows backslash-before-quote rules are preserved.
  auto append=[&](const KV* node,const char* source) {
   if(!node||node->value.empty())return;
   const auto& text=node->value;size_t p=0;
   while(p<text.size()) {
    while(p<text.size()&&std::isspace(static_cast<unsigned char>(text[p])))++p;
    if(p==text.size())break;
    std::string value;bool quoted=false;
    while(p<text.size()&&(quoted||!std::isspace(static_cast<unsigned char>(text[p])))) {
     size_t slashes=0;while(p<text.size()&&text[p]=='\\'){++slashes;++p;}
     if(p<text.size()&&text[p]=='"') {
      value.append(slashes/2,'\\');
      if(slashes%2)value+='"';else quoted=!quoted;
      ++p;
     }else {value.append(slashes,'\\');if(p<text.size()&&(quoted||!std::isspace(static_cast<unsigned char>(text[p]))))value+=text[p++];}
    }
    if(quoted)throw std::runtime_error(std::string(source)+": unterminated command-line quote");
    arguments.push_back(std::move(value));
   }
   std::printf("Adding arguments from %s: %s\n",source,text.c_str());
  };
  append(defaults,"gameinfo");
  const auto config=ReadKV(game/"cfg/commandline.cfg");
  const auto commands=Child(config,"commandline");
  const auto entry=commands?Child(commands->children,FilePath(script).stem().string()):nullptr;
  append(entry?Child(entry->children,"studiomdl"):nullptr,"cfg");
  return true;
 }catch(const std::exception& e){if(err)*err="default arguments: "+std::string(e.what());return false;}
}
bool Initialize(const std::string& gameDirectory,const std::string& steamDirectory,std::string* err) {
 try {
  state.mounts.clear();state.contentMounts.clear();state.contentSearch=false;state.csgoTarget=false;state.targetVtx=-1;state.gameDirectory.clear();if(gameDirectory.empty())return true;
  state.gameDirectory=fs::absolute(FilePath(gameDirectory));
  fs::path game=fs::absolute(FilePath(gameDirectory));auto kv=ReadKV(game/"gameinfo.txt");if(kv.empty())return true;
  const auto root=Child(kv,"gameinfo");const auto system=root?Child(root->children,"filesystem"):nullptr;
  const auto app=system?Child(system->children,"steamappid"):nullptr;
  if(app && (app->value=="730" || app->value=="1012110"))state.targetVtx=1;
  state.csgoTarget=app&&app->value=="730";
  const auto search=system?Child(system->children,"searchpaths"):nullptr;if(!search)return true;
  auto steam=SteamRoot(steamDirectory);std::map<std::string,fs::path> apps;
  for(const auto& n:search->children){auto key=Lower(n.key);if(key.find("game")==std::string::npos&&key.find("mod")==std::string::npos&&key!="content")continue;
   std::string value=n.value;bool prefixed=value.rfind("|",0)==0;fs::path base=game.parent_path();
   if(value.rfind("|gameinfo_path|",0)==0){base=game;value.erase(0,15);}
   else if(value.rfind("|all_source_engine_paths|",0)==0){value.erase(0,25);}
   else if(value.rfind("|appid_",0)==0){auto end=value.find('|',1);if(end==std::string::npos)throw std::runtime_error("unterminated AppID search path");auto id=value.substr(7,end-7);
    auto found=apps.find(id);if(found==apps.end())found=apps.emplace(id,AppDirectory(steam,id)).first;
    if(found->second.empty()){std::fprintf(stderr,"warning: mounted AppID %s is not installed\n",id.c_str());continue;}
    base=found->second;value.erase(0,end+1);}
   if(prefixed)while(!value.empty()&&(value[0]=='/'||value[0]=='\\'))value.erase(0,1);
   auto p=FilePath(value);p=p.is_absolute()?p:base/p;
   Add(p,key=="content");
  }return true;
 }catch(const std::exception& e){if(err)*err="resource mount: "+std::string(e.what());return false;}
}
int TargetVtxFormat(){return state.targetVtx;}
bool IsCsgoTarget(){return state.csgoTarget;}
void EnableContentSearch(){state.contentSearch=true;}
fs::path Find(const fs::path& input) {
 fs::path relative=input;
 if(input.is_absolute()){if(state.cache.empty())return {};relative=input.lexically_relative(state.cache);}
 relative=relative.lexically_normal();if(!SafeRelative(relative))return {};
 std::vector<Mount*> active;for(auto& m:state.mounts)active.push_back(&m);
 if(state.contentSearch)for(auto& m:state.contentMounts)active.push_back(&m);
 for(auto* mount:active){auto& m=*mount;std::error_code ec;if(fs::is_directory(m.path,ec)){auto p=m.path/relative;if(fs::is_regular_file(p,ec))return p;continue;}
  if(Lower(m.path.extension().string())!=".vpk")continue;Index(m);auto found=m.entries.find(Lower(relative.generic_string()));if(found==m.entries.end())continue;
  if(state.cache.empty()){auto root=fs::temp_directory_path().lexically_normal();state.cache=root/("newpage-mount-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));if(!fs::create_directory(state.cache))throw std::runtime_error("cannot create resource cache");}
  auto output=state.cache/relative;fs::create_directories(output.parent_path());const auto& e=found->second;
  auto archive=m.path;uint64_t offset=m.dataStart+e.offset;
  if(e.archive!=0x7fff){auto name=m.path.stem().string();if(name.size()>4&&name.substr(name.size()-4)=="_dir")name.resize(name.size()-4);
   char index[16];std::snprintf(index,sizeof(index),"_%03u.vpk",e.archive);archive=m.path.parent_path()/(name+index);offset=e.offset;}
  std::ifstream f(archive,std::ios::binary|std::ios::ate);auto length=f.tellg();if(!f||length<0||offset>uint64_t(length)||e.length>uint64_t(length)-offset)throw std::runtime_error("VPK entry exceeds archive: "+relative.string());
  std::ofstream out(output,std::ios::binary);out.write(e.preload.data(),e.preload.size());f.seekg(offset);
  char buffer[65536];uint32_t left=e.length;while(left){size_t size=std::min<size_t>(left,sizeof(buffer));f.read(buffer,size);out.write(buffer,size);if(!f||!out)throw std::runtime_error("cannot extract VPK resource");left-=uint32_t(size);}
  dependencies::Note(archive.string());return output;
 }
 return {};
}
namespace {
fs::path MaterialPath(const std::string& name) {
 auto relative=FilePath(name).lexically_normal();
 if(!SafeRelative(relative))return {};
 auto key=Lower(relative.generic_string());
 if(key.rfind("materials/",0)!=0)relative=fs::path("materials")/relative;
 if(Lower(relative.extension().string())!=".vmt")relative+=".vmt";
 if(auto path=Find(relative);!path.empty())return path;
 // Minimal -game directories without gameinfo still have a material root.
 if(state.mounts.empty()&&!state.gameDirectory.empty()) {
  auto path=state.gameDirectory/relative;std::error_code ec;
  if(fs::is_regular_file(path,ec))return path;
 }
 return {};
}
std::optional<std::string> ClientShader(const fs::path& path,std::set<fs::path>& active) {
 if(active.size()>=32||!active.insert(path).second)throw std::runtime_error("cyclic or deeply nested VMT include");
 const auto kv=ReadKV(path);
 if(kv.size()!=1)throw std::runtime_error("VMT requires one shader block");
 auto params=kv.front().children;
 std::optional<std::string> value;
 if(Lower(kv.front().key)=="patch") {
  const auto include=Child(params,"include");
  if(!include)throw std::runtime_error("Patch material is missing include");
  auto base=MaterialPath(include->value);
  if(base.empty())throw std::runtime_error("Patch include not found: "+include->value);
  value=ClientShader(base,active);
  if(const auto insert=Child(params,"insert"))
   if(const auto shader=Child(insert->children,"$clientshader");shader&&!value)value=shader->value;
  if(const auto replace=Child(params,"replace"))
   if(const auto shader=Child(replace->children,"$clientshader");shader&&value)value=shader->value;
 } else if(const auto shader=Child(params,"$clientshader"))value=shader->value;
 active.erase(path);return value;
}
}
std::optional<std::string> MaterialClientShader(const std::string& material,const std::vector<std::string>& directories) {
 for(const auto& directory:directories) {
  const auto path=MaterialPath((FilePath(directory)/FilePath(material)).generic_string());
  if(path.empty())continue;
  try {std::set<fs::path> active;return ClientShader(path,active);}
  catch(const std::exception& e){std::fprintf(stderr,"warning: material %s: %s\n",path.string().c_str(),e.what());return {};}
 }
 return {};
}
void Print(){for(const auto& m:state.mounts)std::printf("Mounted resource: %s\n",m.path.string().c_str());}
}
