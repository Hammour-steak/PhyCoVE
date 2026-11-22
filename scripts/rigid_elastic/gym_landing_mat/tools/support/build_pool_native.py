"""CPU-only SM86 build of the frozen constitutive kernels (tools/viscosity_plugin); no GPU execution."""

from pathlib import Path
import hashlib,json,os,subprocess,sysconfig,pybind11,socket

here=Path(__file__).resolve();root=here.parents[5]
build=root/'.runtime/gym_landing_mat/native';build.mkdir(parents=True,exist_ok=True)
old=root/'tools/viscosity_plugin';source=root/'tools/libuipc_source';deps=old/'deps';native=root/'tools/ipc_probe_deps/uipc/_native'
for name in ['native_viscosity.cu','native_viscosity_frontend.cpp']:
    (build/name).write_bytes((root/'scripts'/('pcve_'+name)).read_bytes())
original={k:v for k,v in json.loads((old/'build_manifest.json').read_text()).items() if k not in ('built_in','runpath','previous_build','cuda_toolkit')}
includes=[old/'error_reporting_shim',source/'include',source/'src',source/'src/backends/cuda',source/'src/backends/cuda/cuda_tool',deps/'eigen',deps/'fmt/include',deps/'spdlog/include',deps/'json/include',deps,deps/'aliases',deps/'cpptrace/include',Path('/usr/local/cuda/include')]
defines=['-DFMT_HEADER_ONLY=1','-DSPDLOG_FMT_EXTERNAL=1','-DUIPC_RUNTIME_CHECK=0','-DUIPC_RELATIVE_SOURCE_FILE="pcve_native_viscosity"']
options=defines+['-I'+str(path)for path in includes]
compiler='/usr/bin/g++-11'
commands=[['/usr/local/cuda/bin/nvcc','-std=c++20','-O2','-arch=sm_86','-ccbin',compiler,'--expt-relaxed-constexpr','--extended-lambda','-Xcompiler=-fPIC',*options,'-c',str(build/'native_viscosity.cu'),'-o',str(build/'viscosity.o')],
          [compiler,'-std=c++20','-O2','-fPIC',*options,'-I'+pybind11.get_include(),'-I'+sysconfig.get_paths()['include'],'-c',str(build/'native_viscosity_frontend.cpp'),'-o',str(build/'frontend.o')],
          [compiler,'-shared',str(build/'viscosity.o'),str(build/'frontend.o'),'-L'+str(native),'-Wl,-rpath,$ORIGIN','-luipc_backend_cuda','-luipc_constitution','-luipc_geometry','-luipc_core','-L/usr/local/cuda/lib64','-lcudart','-o',str(build/('pcve_viscosity'+sysconfig.get_config_var('EXT_SUFFIX')))]]
with (build/'build.log').open('w')as log:
    for command in commands:
        print('CPU_BUILD',command[0],flush=True)
        subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,CUDA_VISIBLE_DEVICES=''))
binary=build/('pcve_viscosity'+sysconfig.get_config_var('EXT_SUFFIX'))
manifest=dict(original,module=str(binary),sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),cuda_architecture='sm_86',cpu_build_host=socket.gethostname(),gpu_compute_during_build=False,commands=commands)
(build/'build_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('CPU_NATIVE_BUILD_COMPLETE',manifest['sha256'],flush=True)
