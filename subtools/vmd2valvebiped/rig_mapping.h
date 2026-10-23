// Versioned, strict human-authored profiles for the existing humanoid solver.
// This maps named anatomical roles; it does not infer arbitrary skeletons.
struct RigProfile {
    bool enabled = false, keepUpright = false, customBasis = false;
    std::string legMode = "ik";
    float motionScale = 1.0f;
    Vector3 left{}, up{};
    std::map<std::string, std::string> roles;
};

std::set<std::string> HumanoidRoles() {
    std::set<std::string> roles;
    for (const auto& item : kMap) {
        if (item.sided) {
            roles.insert(std::string("L_") + item.valve);
            roles.insert(std::string("R_") + item.valve);
        } else roles.insert(item.valve);
    }
    return roles;
}

RigProfile LoadRigProfile(const std::string& path) {
    RigProfile profile;
    if (path.empty()) return profile;
    profile.enabled = true;
    std::ifstream file(fs::u8path(path), std::ios::binary | std::ios::ate);
    if (!file || file.tellg() < 0 || file.tellg() > 65536)
        throw std::runtime_error("cannot read mapping profile, or profile exceeds 64 KiB: " + path);
    file.seekg(0);
    const auto roles = HumanoidRoles();
    std::set<std::string> directives;
    bool header = false;
    size_t lineNo = 0;
    std::string line;
    while (std::getline(file, line)) {
        ++lineNo;
        std::istringstream input(line);
        std::string field;
        if (!(input >> field) || field[0] == '#') continue;
        auto fail = [&](const std::string& why) {
            throw std::runtime_error(path + ":" + std::to_string(lineNo) + ": " + why);
        };
        auto number = [&]() {
            std::string token;
            float value = 0;
            if (!(input >> token) || !ParseFloatOption(token.c_str(), value))
                fail("expected a complete finite number");
            return value;
        };
        if (!header) {
            std::string version;
            if (field != "vmd_humanoid_mapping" || !(input >> version) || version != "1")
                fail("expected vmd_humanoid_mapping 1");
            header = true;
        } else if (field == "role") {
            std::string role, bone;
            if (!(input >> role >> std::quoted(bone)) || !roles.count(role) ||
                !mdldecompiler::CleanName(bone)) fail("role needs a known anatomical role and a valid target bone name");
            if (!profile.roles.emplace(role, bone).second) fail("duplicate role " + role);
        } else {
            if (!directives.insert(field).second) fail("duplicate directive " + field);
            if (field == "leg_mode") {
                if (!(input >> profile.legMode) || (profile.legMode != "fk" && profile.legMode != "ik"))
                    fail("leg_mode must be fk or ik");
            } else if (field == "motion_scale") {
                profile.motionScale = number();
                if (profile.motionScale <= 0 || profile.motionScale > 1000000)
                    fail("motion_scale must be above zero and at most 1000000");
            } else if (field == "upright") {
                std::string mode;
                if (!(input >> mode) || (mode != "auto" && mode != "keep")) fail("upright must be auto or keep");
                profile.keepUpright = mode == "keep";
            } else if (field == "basis") {
                profile.left.x = number(); profile.left.y = number(); profile.left.z = number();
                profile.up.x = number(); profile.up.y = number(); profile.up.z = number();
                if (std::fabs(Len(profile.left) - 1) > 1e-4f || std::fabs(Len(profile.up) - 1) > 1e-4f ||
                    std::fabs(Dot(profile.left, profile.up)) > 1e-4f)
                    fail("basis left and up must be orthogonal unit vectors in target model space");
                profile.customBasis = true;
            } else fail("unknown mapping directive " + field);
        }
        input >> std::ws;
        if (!input.eof() && input.peek() != '#') fail("unexpected trailing mapping data");
    }
    if (file.bad()) throw std::runtime_error("cannot finish reading mapping profile: " + path);
    if (!header || !directives.count("leg_mode"))
        throw std::runtime_error("mapping profile needs its version header and explicit leg_mode");
    return profile;
}

void ApplyRigProfile(const RigProfile& profile, Target& target) {
    if (!profile.enabled) return;
    std::map<int, std::string> owners;
    for (const auto& role : HumanoidRoles()) {
        const auto custom = profile.roles.find(role);
        const std::string name = custom == profile.roles.end() ? "ValveBiped.Bip01_" + role : custom->second;
        int found = -1;
        for (int i = 0; i < target.n; ++i)
            if (_stricmp(target.names[i].c_str(), name.c_str()) == 0) {
                if (found >= 0) throw std::runtime_error("ambiguous target bone " + name);
                found = i;
            }
        if (found < 0) {
            if (custom != profile.roles.end()) throw std::runtime_error("mapping target bone not found: " + name);
            continue;
        }
        const auto [owner, inserted] = owners.emplace(found, role);
        if (!inserted) throw std::runtime_error("mapping roles " + owner->second + " and " + role + " share target bone " + name);
        target.roles.emplace(role, found);
    }
    for (const char* role : {"Pelvis", "L_Thigh", "R_Thigh", "L_Calf", "R_Calf", "L_Foot", "R_Foot"})
        if (target.Find(role) < 0) throw std::runtime_error(std::string("mapping needs humanoid role ") + role);
    for (const char* side : {"L_", "R_"}) {
        const int thigh = target.Find(std::string(side) + "Thigh");
        const int calf = target.Find(std::string(side) + "Calf");
        const int foot = target.Find(std::string(side) + "Foot");
        if (target.parent[calf] != thigh || target.parent[foot] != calf)
            throw std::runtime_error(std::string("mapping leg must be a direct Thigh -> Calf -> Foot chain: ") + side);
    }
}
