// Standalone track exports share the native durable publication transaction.
// Included after the VMD readers/writers inside main.cpp's private namespace.

bool ReadControllers(const Mdl& model, std::vector<mdldecompiler::FlexTrack>& out,
                     std::string& err) {
    const auto& h = *model.hdr;
    const auto* controllers = model.At<fm::mstudioflexcontroller_t>(
        model.buf.data(), h.flexcontrollerindex, h.numflexcontrollers);
    if (h.numflexcontrollers < 0 || (h.numflexcontrollers && !controllers)) {
        err = "invalid target flex controller table";
        return false;
    }
    std::set<std::string> names;
    for (int i = 0; i < h.numflexcontrollers; ++i) {
        const auto& c = controllers[i];
        const std::string name = model.Str(&c, c.sznameindex);
        if (!mdldecompiler::CleanName(name) ||
            !names.insert(mdldecompiler::BoneNameKey(name)).second ||
            !std::isfinite(c.min) || !std::isfinite(c.max) || c.min >= c.max) {
            err = "invalid or ambiguous target flex controller #" + std::to_string(i);
            return false;
        }
        out.push_back({name, c.min, c.max, {}});
    }
    return true;
}

int RunTrackMode(const std::string& mode, const std::vector<std::string>& inputs,
                 const std::string& mdlPath, const std::string& output, const std::string& faceMapPath,
                 const FaceMap& faceMap, long start, long end, bool uncompress, float eyeRange,
                 float cameraScale, bool fovBone) {
    std::string err;
    Mdl target;
    std::vector<mdldecompiler::FlexTrack> controllers;
    if (mode == "face") {
        if (!LoadMdl(mdlPath, target, err) || !ReadControllers(target, controllers, err)) return Fail(err);
        if (controllers.empty()) return Fail("-mode face needs target flex controllers from -mdl");
    }
    struct Job {
        std::string source, destination, smd, clip;
        std::map<std::string, std::vector<Key>> keys;
        Morphs morphs;
        std::vector<CamKey> cameras;
        uint32_t last = 0;
    };
    std::vector<Job> jobs;
    std::set<fs::path::string_type, OutputPathLess> destinations;
    std::vector<fs::path> protectedInputs;
    for (const auto& path : inputs) protectedInputs.push_back(fs::weakly_canonical(fs::u8path(path)));
    if (!mdlPath.empty()) protectedInputs.push_back(fs::weakly_canonical(fs::u8path(mdlPath)));
    if (!faceMapPath.empty()) protectedInputs.push_back(fs::weakly_canonical(fs::u8path(faceMapPath)));
    auto reserve = [&](const std::string& path) {
        const fs::path resolved = fs::weakly_canonical(fs::absolute(fs::u8path(path)));
        for (const auto& input : protectedInputs) {
            std::error_code ec;
            if ((!OutputPathLess{}(resolved.native(), input.native()) &&
                 !OutputPathLess{}(input.native(), resolved.native())) || fs::equivalent(resolved, input, ec))
                throw std::runtime_error("output aliases an input: " + path);
        }
        for (const auto& previous : destinations) {
            std::error_code ec;
            if (fs::equivalent(resolved, fs::path(previous), ec))
                throw std::runtime_error("output collision: " + path);
        }
        if (!destinations.insert(resolved.native()).second)
            throw std::runtime_error("output collision: " + path);
    };
    for (const auto& source : inputs) {
        Job job;
        job.source = source;
        uint32_t ignored;
        if (!LoadVmd(source, job.keys, job.morphs, job.cameras, ignored, err)) return Fail(err);
        if (mode == "camera") {
            if (job.cameras.empty()) return Fail("\"" + source + "\": no camera keys to export");
            if (!CameraProjectionSupported(job.cameras, source, err)) return Fail(err);
            job.last = job.cameras.back().frame;
        } else {
            for (const auto& [name, keys] : job.morphs)
                if (!keys.empty()) job.last = std::max(job.last, keys.back().frame);
            for (const char* eye : kEyeBones)
                if (job.keys.count(eye) && !job.keys[eye].empty())
                    job.last = std::max(job.last, job.keys[eye].back().frame);
        }
        if (job.last >= static_cast<uint32_t>(LONG_MAX))
            return Fail("motion frame range exceeds the supported integer range");
        job.destination = output.empty() ? mdldecompiler::StripExt(source) + ".dmx" : output;
        if (mdldecompiler::BoneNameKey(fs::u8path(job.destination).extension().u8string()) != ".dmx")
            return Fail("standalone -o must name a .dmx file");
        job.clip = mdldecompiler::OutputStem(mdldecompiler::StripExt(mdldecompiler::BaseName(job.destination)), "motion");
        reserve(job.destination);
        if (mode == "camera") {
            job.smd = mdldecompiler::StripExt(job.destination) + ".smd";
            reserve(job.smd);
        }
        jobs.push_back(std::move(job));
    }
    subtool::OutputTransaction outputs;
    for (const auto& job : jobs) {
        const long first = start < 0 ? 0 : start;
        const long last = end < 0 ? job.last : std::min<long>(end, job.last);
        if (first > last) return Fail("\"" + job.source + "\": -start is past -end or the last selected track key");
        const long span = last - first;
        const long count = uncompress ? span + 1 : std::min<long>(span + 1, pulse::limits::kMaxAnimFrames);
        const float fps = count == span + 1 ? 30.0f : static_cast<float>(30.0 * (count - 1) / span);
        std::vector<float> times;
        for (long i = 0; i < count; ++i)
            times.push_back(static_cast<float>(first + (count > 1 ? double(span) * i / (count - 1) : 0.0)));
        if (mode == "camera") {
            std::vector<AnimPose> poses;
            std::vector<float> fovs;
            // MMD X/Y/Z -> Source X/Z/Y. Standalone clips have no character
            // anchor; the explicit scale is Source units per MMD unit.
            auto basis = [](const Vector3& v) { return Vector3{v.x, v.z, v.y}; };
            for (float time : times) {
                Vector3 eye, look, up;
                float fov;
                SampleCamera(job.cameras, time, eye, look, up, fov);
                eye = Mul(basis(eye), cameraScale); look = basis(look); up = basis(up);
                const Vector3 left = Cross(up, look);
                matrix3x4 transform;
                for (int row = 0; row < 3; ++row) {
                    transform.m[row][0] = (&look.x)[row];
                    transform.m[row][1] = (&left.x)[row];
                    transform.m[row][2] = (&up.x)[row];
                }
                SetOrigin(transform, eye);
                AnimPose pose;
                pm::MatrixAngles(transform, pose.rot, pose.pos);
                if (!FiniteMatrix(transform) || !FinitePose(pose) || !std::isfinite(fov))
                    return Fail("non-finite standalone camera pose");
                poses.push_back(pose); fovs.push_back(fov);
            }
            if (!WriteCameraSmd(outputs.Stage(job.smd), poses, fovBone ? &fovs : nullptr) ||
                !mdldecompiler::WriteCameraDmx(outputs.Stage(job.destination), job.clip, fps, poses, fovs))
                return Fail("cannot write standalone camera outputs");
        } else {
            std::set<std::string> missing;
            int unmapped = 0;
            auto face = FaceTracks(job.morphs, faceMap, controllers, times, missing, unmapped);
            AddEyeTracks(job.keys, controllers, times, eyeRange, face);
            if (face.empty()) return Fail("\"" + job.source + "\": no facial tracks map to the target controllers");
            for (const auto& name : missing) std::printf("unavailable target flex controller: %s\n", name.c_str());
            if (unmapped) std::printf("%d morph tracks have no face-map entry\n", unmapped);
            // A face-only clip must not drive every target bone to its bind
            // pose. A skeleton-free model emits only controller channels.
            Mdl faceModel;
            faceModel.buf.resize(sizeof(fm::studiohdr_t));
            faceModel.hdr = reinterpret_cast<const fm::studiohdr_t*>(faceModel.buf.data());
            std::vector<std::vector<AnimPose>> frames(static_cast<size_t>(count));
            if (!mdldecompiler::WriteAnimationDmx(faceModel, outputs.Stage(job.destination), job.clip, fps, frames, &face))
                return Fail("cannot write standalone facial clip");
        }
        std::printf("prepared %s: %ld frames at %.9g fps (source frames %ld..%ld)\n",
                    job.destination.c_str(), count, fps, first, last);
    }
    outputs.Commit();
    std::printf("all standalone track outputs published successfully\n");
    return 0;
}
