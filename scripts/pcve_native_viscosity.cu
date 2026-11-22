// SPDX-License-Identifier: Apache-2.0
// PhyCoVE: incremental objective metric and dihedral viscosity. The energy,
// its exact gradient and exact Hessian with PSD projection enter the SAME IPC solve.
#include <finite_element/finite_element_extra_constitution.h>
#include <uipc/builtin/attribute_name.h>
#include <utils/matrix_assembler.h>
#include <utils/dihedral_angle.h>
#include <utils/make_spd.h>
#include <map>
#include <array>

namespace uipc::backend::cuda {
namespace {
constexpr U64 ViscosityUID=(1ull<<32)+101;
using Gradients=Matrix<Float,3,4>;

__global__ void metric_energy(
 cuda_tool::CBufferView<Vector4i> ids,cuda_tool::CBufferView<Gradients> gradients,
 cuda_tool::CBufferView<Vector4> params,cuda_tool::CBufferView<Vector3> x,
 cuda_tool::CBufferView<Vector3> previous,cuda_tool::BufferView<Float> energy,
 Float dt,int n) {
 int k=blockIdx.x*blockDim.x+threadIdx.x;if(k>=n)return;
 const auto t=ids(k);const auto g=gradients(k);const auto p=params(k);
 int d=(int)p[3],nv=d+1;Matrix3x3 F=Matrix3x3::Zero(),Fn=F;
 for(int i=0;i<nv;++i){F+=x(t[i])*g.col(i).transpose();Fn+=previous(t[i])*g.col(i).transpose();}
 Matrix3x3 D=.5*(F.transpose()*F-Fn.transpose()*Fn);
 Float tr=D.trace();energy(k)=p[2]*dt*(p[0]*(D.squaredNorm()-tr*tr/d)+.5*p[1]*tr*tr);
}

__global__ void metric_derivatives(
 cuda_tool::CBufferView<Vector4i> ids,cuda_tool::CBufferView<Gradients> gradients,
 cuda_tool::CBufferView<Vector4> params,cuda_tool::CBufferView<Vector3> x,
 cuda_tool::CBufferView<Vector3> previous,cuda_tool::DoubletVectorView<Float,3> G,
 cuda_tool::TripletMatrixView<Float,3> H,Float dt,bool gradient_only,int n) {
 int k=blockIdx.x*blockDim.x+threadIdx.x;if(k>=n)return;
 const auto t=ids(k);const auto g=gradients(k);const auto p=params(k);
 int d=(int)p[3],nv=d+1;Matrix3x3 F=Matrix3x3::Zero(),Fn=F;
 for(int i=0;i<nv;++i){F+=x(t[i])*g.col(i).transpose();Fn+=previous(t[i])*g.col(i).transpose();}
 Matrix3x3 D=.5*(F.transpose()*F-Fn.transpose()*Fn),Id=Matrix3x3::Zero();
 for(int i=0;i<d;++i)Id(i,i)=1;
 Matrix3x3 S=2*p[0]*D+(p[1]-2*p[0]/d)*D.trace()*Id;
 Matrix3x3 P=p[2]*dt*F*S;DoubletVectorAssembler assembler{G};
 // A repeated last vertex supplies the fourth zero contribution for triangles.
 for(int i=0;i<4;++i){Vector3 value=i<nv ? Vector3(P*g.col(i)) : Vector3::Zero();assembler(k*4+i).write(t[i],value);}
 if(gradient_only)return;
 Matrix3x3 FFt=F*F.transpose();Matrix9x9 tangent=Matrix9x9::Zero();
 for(int a=0;a<d;++a)for(int b=0;b<d;++b){
  Matrix3x3 block=p[0]*((a==b?FFt:Matrix3x3::Zero())+F.col(b)*F.col(a).transpose())+(p[1]-2*p[0]/d)*F.col(a)*F.col(b).transpose()+S(a,b)*Matrix3x3::Identity();
  tangent.block<3,3>(3*a,3*b)=block;
 }
 make_spd(tangent);int offset=k*10;
 for(int i=0;i<4;++i)for(int j=i;j<4;++j){
  int a=i,b=j;if(t[a]>t[b]){a=j;b=i;}Matrix3x3 block=Matrix3x3::Zero();
  if(a<nv&&b<nv)for(int c=0;c<d;++c)for(int e=0;e<d;++e)block+=p[2]*dt*g(c,a)*g(e,b)*tangent.block<3,3>(3*c,3*e);
  H(offset++).write(t[a],t[b],block);
 }
}

__device__ Float hinge_delta(const Vector4i& t,cuda_tool::CBufferView<Vector3> x,
 cuda_tool::CBufferView<Vector3> previous) {
 Float a,b;dihedral_angle(x(t[0]),x(t[1]),x(t[2]),x(t[3]),a);
 dihedral_angle(previous(t[0]),previous(t[1]),previous(t[2]),previous(t[3]),b);
 return atan2(sin(a-b),cos(a-b));
}
__global__ void hinge_energy(cuda_tool::CBufferView<Vector4i> ids,
 cuda_tool::CBufferView<Float> coefficients,cuda_tool::CBufferView<Vector3> x,
 cuda_tool::CBufferView<Vector3> previous,cuda_tool::BufferView<Float> energy,Float dt,int n) {
 int k=blockIdx.x*blockDim.x+threadIdx.x;if(k>=n)return;
 Float d=hinge_delta(ids(k),x,previous);energy(k)=.5*dt*coefficients(k)*d*d;
}
__global__ void hinge_derivatives(cuda_tool::CBufferView<Vector4i> ids,
 cuda_tool::CBufferView<Float> coefficients,cuda_tool::CBufferView<Vector3> x,
 cuda_tool::CBufferView<Vector3> previous,cuda_tool::DoubletVectorView<Float,3> G,
 cuda_tool::TripletMatrixView<Float,3> H,Float dt,bool gradient_only,int n) {
 int k=blockIdx.x*blockDim.x+threadIdx.x;if(k>=n)return;
 auto t=ids(k);Float d=hinge_delta(t,x,previous);Vector12 q;
 dihedral_angle_gradient(x(t[0]),x(t[1]),x(t[2]),x(t[3]),q);
 Float c=dt*coefficients(k);DoubletVectorAssembler assembler{G};
 assembler.segment<4>(k*4).write(t,c*d*q);
 if(gradient_only)return;
 Matrix12x12 curvature;dihedral_angle_hessian(x(t[0]),x(t[1]),x(t[2]),x(t[3]),curvature);
 Matrix12x12 block=c*(q*q.transpose()+d*curvature);make_spd(block);TripletMatrixAssembler matrix{H};matrix.half_block<4>(k*10).write(t,block);
}
// Unrecorded static preparation only. Cancel part of the native inertia while
// retaining the ORIGINAL gravitational force and original contact mass bounds.
// Canonical dynamics has no such vertices and never launches these kernels.
__global__ void preparation_energy(cuda_tool::CBufferView<IndexT> ids,
 cuda_tool::CBufferView<Vector4> params,cuda_tool::CBufferView<Float> masses,
 cuda_tool::CBufferView<Vector3> x,cuda_tool::CBufferView<Vector3> predicted,
 cuda_tool::BufferView<Float> energy,Float dt,int n){
 int k=blockIdx.x*blockDim.x+threadIdx.x;if(k>=n)return;auto i=ids(k);auto p=params(k);Float mass=masses(i),a=(p[0]-1)*mass;Vector3 gravity=p.tail<3>(),d=x(i)-predicted(i);
 energy(k)=.5*a*d.squaredNorm()-(1-p[0])*dt*dt*mass*gravity.dot(x(i));
}
__global__ void preparation_derivatives(cuda_tool::CBufferView<IndexT> ids,
 cuda_tool::CBufferView<Vector4> params,cuda_tool::CBufferView<Float> masses,
 cuda_tool::CBufferView<Vector3> x,cuda_tool::CBufferView<Vector3> predicted,
 cuda_tool::DoubletVectorView<Float,3> G,cuda_tool::TripletMatrixView<Float,3> H,
 Float dt,bool gradient_only,int n){
 int k=blockIdx.x*blockDim.x+threadIdx.x;if(k>=n)return;auto i=ids(k);auto p=params(k);Float mass=masses(i),a=(p[0]-1)*mass;Vector3 gradient=a*(x(i)-predicted(i))-(1-p[0])*dt*dt*mass*p.tail<3>();
 DoubletVectorAssembler assembler{G};assembler(k).write(i,gradient);
 if(!gradient_only){Matrix3x3 block=a*Matrix3x3::Identity();H(k).write(i,i,block);}
}
}

class PCVEMetricViscosity final:public FiniteElementExtraConstitution {
public:
 using FiniteElementExtraConstitution::FiniteElementExtraConstitution;
 cuda_tool::DeviceBuffer<Vector4i> elements,hinges;
 cuda_tool::DeviceBuffer<Gradients> shape_gradients;
 cuda_tool::DeviceBuffer<Vector4> coefficients;
 cuda_tool::DeviceBuffer<Float> hinge_coefficients;
 cuda_tool::DeviceBuffer<IndexT> preparation_ids;
 cuda_tool::DeviceBuffer<Vector4> preparation_params;
 FiniteElementMethod* fem=nullptr;
 virtual U64 get_uid()const noexcept override{return ViscosityUID;}
 virtual void do_build(BuildInfo&)override{fem=&require<FiniteElementMethod>();}
 virtual void do_init(FilteredInfo& info)override {
  std::vector<Vector4i> tets,hs;std::vector<Gradients> gs;std::vector<Vector4> ps;std::vector<Float> hc;
  std::vector<IndexT> prep_ids;std::vector<Vector4> prep_params;
  auto rest=info.rest_positions();
  info.for_each(world().scene().geometries(),[&](const FiniteElementMethod::ForEachInfo&,geometry::SimplicialComplex& sc){
   int offset=sc.meta().find<IndexT>(builtin::backend_fem_vertex_offset)->view().front();
   if(auto scale=sc.meta().find<Float>("pcve_preparation_inertia_scale");scale&&scale->view().front()<1){
    Vector4 parameter;parameter[0]=scale->view().front();parameter.tail<3>()=sc.meta().find<Vector3>("pcve_preparation_gravity")->view().front();
    for(IndexT i=0;i<sc.vertices().size();++i){prep_ids.push_back(offset+i);prep_params.push_back(parameter);}
   }
   Float eta=sc.meta().find<Float>("pcve_viscosity_eta")->view().front();
   Float zeta=sc.meta().find<Float>("pcve_viscosity_zeta")->view().front();
   Float cb=sc.meta().find<Float>("pcve_bending_viscosity")->view().front();
   int dim=sc.dim();
   if(dim==3){for(auto t:sc.tetrahedra().topo().view()){
    t.array()+=offset;Matrix3x3 D;for(int j=0;j<3;++j)D.col(j)=rest[t[j+1]]-rest[t[0]];
    Gradients g;g.rightCols<3>()=D.inverse().transpose();g.col(0)=-g.rightCols<3>().rowwise().sum();
    tets.push_back(t);gs.push_back(g);ps.emplace_back(eta,zeta,std::abs(D.determinant())/6,3);
   }}else if(dim==2){
    std::map<std::pair<int,int>,std::vector<int>> edges;
    for(auto tri:sc.triangles().topo().view()){
     tri.array()+=offset;Vector3 a=rest[tri[1]]-rest[tri[0]],b=rest[tri[2]]-rest[tri[0]];
     Float length=a.norm(),bx=b.dot(a)/length,by=std::sqrt(std::max(Float(0),b.squaredNorm()-bx*bx));
     Gradients g=Gradients::Zero();g(0,1)=1/length;g(1,1)=-bx/(length*by);g(1,2)=1/by;g.col(0)=-g.col(1)-g.col(2);
     tets.emplace_back(tri[0],tri[1],tri[2],tri[2]);gs.push_back(g);ps.emplace_back(eta,zeta,length*by/2,2);
     for(int k=0;k<3;++k){int i=tri[k],j=tri[(k+1)%3],op=tri[(k+2)%3];if(i>j)std::swap(i,j);edges[{i,j}].push_back(op);}
    }
    if(cb>0)for(auto& [edge,op]:edges){if(op.size()!=2)continue;int a=edge.first,b=edge.second;
     Float L2=(rest[b]-rest[a]).squaredNorm();Float area=.5*((rest[a]-rest[op[0]]).cross(rest[b]-rest[op[0]]).norm()+(rest[b]-rest[op[1]]).cross(rest[a]-rest[op[1]]).norm());
     hs.emplace_back(op[0],a,b,op[1]);hc.push_back(cb*3*L2/area);
    }
   }
  });
  elements.resize(tets.size());elements.view().copy_from(tets.data());shape_gradients.resize(gs.size());shape_gradients.view().copy_from(gs.data());coefficients.resize(ps.size());coefficients.view().copy_from(ps.data());
  hinges.resize(hs.size());hinges.view().copy_from(hs.data());hinge_coefficients.resize(hc.size());hinge_coefficients.view().copy_from(hc.data());
  preparation_ids.resize(prep_ids.size());preparation_ids.view().copy_from(prep_ids.data());preparation_params.resize(prep_params.size());preparation_params.view().copy_from(prep_params.data());
  printf("PCVE coupled viscosity: %zu metric elements; %zu bending hinges\n",tets.size(),hs.size());
  if(!prep_ids.empty())printf("PCVE unrecorded static preparation: %zu vertices, reduced inertia; original gravity and contact masses retained\n",prep_ids.size());
 }
 virtual void do_report_extent(ReportExtentInfo& info)override {
  SizeT n=elements.size()+hinges.size(),p=preparation_ids.size();info.energy_count(n+p);info.gradient_count(4*n+p);if(!info.gradient_only())info.hessian_count(10*n+p);
 }
 virtual void do_compute_energy(ComputeEnergyInfo& info)override {
  int n=elements.size(),h=hinges.size();cuda_tool::CBufferView<Vector3> previous=fem->x_prevs();
  if(n)metric_energy<<<(n+127)/128,128>>>(elements.cview(),shape_gradients.cview(),coefficients.cview(),info.xs(),previous,info.energies().subview(0,n),info.dt(),n);
  if(h)hinge_energy<<<(h+127)/128,128>>>(hinges.cview(),hinge_coefficients.cview(),info.xs(),previous,info.energies().subview(n,h),info.dt(),h);
  int p=preparation_ids.size();if(p)preparation_energy<<<(p+127)/128,128>>>(preparation_ids.cview(),preparation_params.cview(),fem->masses(),info.xs(),fem->x_tildes(),info.energies().subview(n+h,p),info.dt(),p);
 }
 virtual void do_compute_gradient_hessian(ComputeGradientHessianInfo& info)override {
  int n=elements.size(),h=hinges.size();cuda_tool::CBufferView<Vector3> previous=fem->x_prevs();bool only=info.gradient_only();
  auto G=info.gradients();auto H=info.hessians();
  if(n)metric_derivatives<<<(n+127)/128,128>>>(elements.cview(),shape_gradients.cview(),coefficients.cview(),info.xs(),previous,G.subview(0,4*n),only?H:H.subview(0,10*n),info.dt(),only,n);
  if(h)hinge_derivatives<<<(h+127)/128,128>>>(hinges.cview(),hinge_coefficients.cview(),info.xs(),previous,G.subview(4*n,4*h),only?H:H.subview(10*n,10*h),info.dt(),only,h);
  int p=preparation_ids.size();if(p)preparation_derivatives<<<(p+127)/128,128>>>(preparation_ids.cview(),preparation_params.cview(),fem->masses(),info.xs(),fem->x_tildes(),G.subview(4*(n+h),p),only?H:H.subview(10*(n+h),p),info.dt(),only,p);
 }
};
REGISTER_SIM_SYSTEM(PCVEMetricViscosity);
}
