"""An explicit effective-modulus adapter for the pinned SNK1 constitution."""
import numpy as np

def mapped_moduli(E,nu):
 mu=E/(2*(1+nu));lam=E*nu/((1+nu)*(1-2*nu))
 input_mu=.75*mu;input_lam=lam+.5*input_mu
 input_E=input_mu*(3*input_lam+2*input_mu)/(input_lam+input_mu);input_nu=input_lam/(2*(input_lam+input_mu))
 return dict(requested_effective_E_pa=float(E),requested_effective_nu=float(nu),input_E_pa=float(input_E),input_nu=float(input_nu),kernel_mu_pa=float(mu),kernel_lambda_pa=float(lam+mu),effective_lame_lambda_pa=float(lam),mapping='mu_s=4*mu_in/3;lambda_s=lambda_in+5*mu_in/6;effective mu=mu_s,effective lambda=lambda_s-mu_s. Inverted here to match the declared E and nu exactly.')

def elastic_energy(F,material):
 J=np.linalg.det(F);return .5*material['kernel_mu_pa']*(np.sum(F*F,axis=(-2,-1))-3-2*(J-1))+.5*material['kernel_lambda_pa']*(J-1)**2
