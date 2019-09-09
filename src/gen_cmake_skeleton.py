import os
import sys
import re

def get_subdirectories(d):
    return [name for name in os.listdir(d) if os.path.isdir(os.path.join(d, name))]

def is_bin_dir(d):
    return d.endswith("bin")

def get_files(d):
    return [name for name in os.listdir(d) if os.path.isfile(os.path.join(d, name))]

def is_header(f):
    return f.endswith(".h")

def is_cu_source(f):
    return f.endswith(".cu")

def is_test_source(f):
    return f.endswith("-test.cc")

def is_source(f):
    return f.endswith(".cc") and not is_test_source(f)

def dir_name_to_lib_target(dir_name):
    return "kaldi-" + dir_name


def get_exe_additional_depends(t):
    additional = {
        "transform-feats" : ["transform"],
        "interpolate-pitch" : ["transform"],
        "post-to-feats" : ["hmm"],
        "append-post-to-feats" : ["hmm"],
        "gmm-est-fmllr-gpost": ["sgmm2", "hmm"],
        "gmm-est-fmllr": ["hmm", "transform"],
        "gmm-latgen-faster": ["decoder"],
        "gmm-transform-means": ["hmm"],
        "gmm-post-to-gpost": ["hmm"],
        "gmm-init-lvtln": ["transform"],
        "gmm-rescore-lattice": ["hmm", "lat"],
        "gmm-est-fmllr-global": ["transform"],
        "gmm-copy": ["hmm"],
        "gmm-train-lvtln-special": ["transform", "hmm"],
        "gmm-est-map": ["hmm"],
        "gmm-acc-stats2": ["hmm"],
        "gmm-decode-faster-regtree-mllr": ["decoder"],
        "gmm-global-est-fmllr": ["transform"],
        "gmm-est-basis-fmllr": ["hmm", "transform"],
        "gmm-init-model": ["hmm"],
        "gmm-est-weights-ebw": ["hmm"],
        "gmm-init-biphone": ["hmm"],
        "gmm-compute-likes": ["hmm"],
        "gmm-est-fmllr-raw-gpost": ["hmm", "transform"],
        "gmm-*": ["hmm", "transform", "lat", "decoder"] # FUCK!
    }
    if t in additional:
        return list(map(lambda name: dir_name_to_lib_target(name), additional[t]))
    elif (t.split("-", 1)[0] + "-*") in additional:
        wildcard = (t.split("-", 1)[0] + "-*")
        return list(map(lambda name: dir_name_to_lib_target(name), additional[wildcard]))
    else:
        return []


class CMakeListsLibrary(object):

    def __init__(self, dir_name):
        self.dir_name = dir_name
        self.target_name = dir_name_to_lib_target(self.dir_name)
        self.file_list = []
        self.cuda_file_list = []
        self.test_file_list = []
        self.depends = []

    def add_test_source(self, filename):
        self.test_file_list.append(filename)

    def add_source(self, filename):
        self.file_list.append(filename)

    def add_cuda_source(self, filename):
        self.cuda_file_list.append(filename)

    def load_dependency_from_makefile(self, filename):
        with open(filename) as f:
            makefile = f.read()
            if "ADDLIBS" not in makefile:
                print("WARNING: non-standard", filename)
                return
            libs = makefile.split("ADDLIBS")[-1].split("\n\n")[0]
            libs = re.findall("[^\s\\\\=]+", libs)
            for l in libs:
                self.depends.append(os.path.splitext(os.path.basename(l))[0])



    def gen_code(self):
        ret = []
        if len(self.cuda_file_list) > 0:
            self.file_list.append("${CUDA_OBJS}")
            ret.append("cuda_include_directories(${CMAKE_CURRENT_SOURCE_DIR}/..)")
            ret.append("cuda_compile(CUDA_OBJS")
            for f in self.cuda_file_list:
                ret.append("    " + f)
            ret.append(")\n")


        ret.append("add_library(" + self.target_name)
        for f in self.file_list:
            ret.append("    " + f)
        ret.append(")\n")
        ret.append("target_include_directories(" + self.target_name + " PUBLIC ")
        ret.append("     $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>")
        ret.append("     $<INSTALL_INTERFACE:include/kaldi>")
        ret.append(")\n")

        if len(self.depends) > 0:
            ret.append("target_link_libraries(" + self.target_name + " PUBLIC")
            for d in self.depends:
                ret.append("    " + d)
            ret.append(")\n")

        def get_test_exe_name(filename):
            exe_name = os.path.splitext(f)[0]
            if self.dir_name.startswith("nnet") and exe_name.startswith("nnet"):
                return self.dir_name + "-" + exe_name.split("-", 1)[1]
            else:
                return exe_name

        if len(self.test_file_list) > 0:
            ret.append("if(KALDI_BUILD_TEST)")
            for f in self.test_file_list:
                exe_target = get_test_exe_name(f)
                depends = (self.target_name + " " + " ".join(get_exe_additional_depends(exe_target))).strip()
                ret.append("    add_kaldi_test_executable(NAME " + exe_target + " SOURCES " + f + " DEPENDS " + depends + ")")
            ret.append("endif()")

        return "\n".join(ret)



class CMakeListsExecutable(object):

    def __init__(self, dir_name, filename):
        assert(dir_name.endswith("bin"))
        self.list = []
        exe_name = os.path.splitext(os.path.basename(filename))[0]
        file_name = filename
        depend = dir_name_to_lib_target(dir_name[:-3])
        self.list.append((exe_name, file_name, depend))

    def gen_code(self):
        ret = []
        for exe_name, file_name, depend in self.list:
            depends = (depend + " " + " ".join(get_exe_additional_depends(exe_name))).strip()
            ret.append("add_kaldi_executable(NAME " + exe_name + " SOURCES " + file_name + " DEPENDS " + depends + ")")
        return "\n".join(ret)

class CMakeListsFile(object):

    def __init__(self, directory):
        self.path = os.path.realpath(os.path.join(directory, "CMakeLists.txt"))
        self.sections = []

    def add_section(self, section):
        self.sections.append(section)

    def write_file(self):
        with open(self.path, "w") as f:
            for s in self.sections:
                code = s.gen_code()
                f.write(code)
                f.write("\n")
        print("  Writed", self.path)


if __name__ == "__main__":

    subdirs = get_subdirectories(".")
    for d in subdirs:
        cmakelists = CMakeListsFile(d)
        if is_bin_dir(d):
            for f in get_files(d):
                if is_source(f):
                    dir_name = os.path.basename(d)
                    filename = os.path.basename(f)
                    exe = CMakeListsExecutable(dir_name, filename)
                    cmakelists.add_section(exe)
        else:
            dir_name = os.path.basename(d)
            lib = CMakeListsLibrary(dir_name)
            makefile = os.path.join(d, "Makefile")
            if not os.path.exists(makefile):
                continue
            lib.load_dependency_from_makefile(makefile)
            cmakelists.add_section(lib)
            for f in get_files(d):
                filename = os.path.basename(f)
                if is_source(filename):
                    lib.add_source(filename)
                elif is_cu_source(filename):
                    lib.add_cuda_source(filename)
                elif is_test_source(filename):
                    lib.add_test_source(filename)

        cmakelists.write_file()
