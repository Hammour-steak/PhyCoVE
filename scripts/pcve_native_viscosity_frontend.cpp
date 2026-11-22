// SPDX-License-Identifier: Apache-2.0
#include <pybind11/pybind11.h>
#include <uipc/constitution/finite_element_extra_constitution.h>
#include <uipc/builtin/constitution_uid_auto_register.h>
#include <uipc/builtin/constitution_type.h>
#include <uipc/geometry/attribute.h>

namespace uipc::constitution {
constexpr U64 ViscosityUID=(1ull<<32)+101;
REGISTER_CONSTITUTION_UIDS(){
 list<builtin::UIDInfo> out;builtin::UIDInfo info;info.uid=ViscosityUID;
 info.name="PCVEIncrementalMetricViscosity";info.type=string{builtin::FiniteElement};
 info.author="PhyCoVE";info.description="Objective metric and dihedral dissipation in the native IPC Newton objective";out.push_back(info);return out;
}
class PCVEViscosity:public FiniteElementExtraConstitution {
public:
 U64 get_uid()const noexcept override{return ViscosityUID;}
 void apply(geometry::SimplicialComplex& sc,Float eta,Float zeta,Float bending){
  if(eta<0||zeta<0||bending<0)throw std::invalid_argument("Viscosities must be nonnegative");
  FiniteElementExtraConstitution::apply_to(sc);
  for(auto [name,value]:{std::pair{"pcve_viscosity_eta",eta},std::pair{"pcve_viscosity_zeta",zeta},std::pair{"pcve_bending_viscosity",bending}}){
   auto a=sc.meta().find<Float>(name);if(!a)a=sc.meta().create<Float>(name);geometry::view(*a).front()=value;
  }
 }
};
}
PYBIND11_MODULE(pcve_viscosity,m){
 m.doc()="Native IPC incrementally objective metric/hinge viscosity, no velocity split";
 m.def("apply_to",[](uipc::geometry::SimplicialComplex& sc,double eta,double zeta,double bending){uipc::constitution::PCVEViscosity{}.apply(sc,eta,zeta,bending);},pybind11::arg("mesh"),pybind11::arg("eta"),pybind11::arg("zeta"),pybind11::arg("bending")=0.);
 m.def("apply_static_preparation_to",[](uipc::geometry::SimplicialComplex& sc,double scale,double gx,double gy,double gz){
  if(!(scale>0.0&&scale<=1.0))throw std::invalid_argument("Preparation inertia scale must lie in (0,1]");
  auto a=sc.meta().find<uipc::Float>("pcve_preparation_inertia_scale");if(!a)a=sc.meta().create<uipc::Float>("pcve_preparation_inertia_scale");uipc::geometry::view(*a).front()=scale;
  auto g=sc.meta().find<uipc::Vector3>("pcve_preparation_gravity");if(!g)g=sc.meta().create<uipc::Vector3>("pcve_preparation_gravity");uipc::geometry::view(*g).front()=uipc::Vector3(gx,gy,gz);
 },pybind11::arg("mesh"),pybind11::arg("inertia_scale"),pybind11::arg("gx"),pybind11::arg("gy"),pybind11::arg("gz"));
 m.attr("uid")=pybind11::int_(uipc::constitution::ViscosityUID);
}
