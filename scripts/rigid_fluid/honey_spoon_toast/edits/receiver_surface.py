"""One measured bread surface shared by simulation and surface reconstruction."""
from pathlib import Path
import numpy as np


class BreadSurface:
    def __init__(self, path):
        self.path=Path(path)
        with np.load(path) as data:
            self.x,self.y,self.z,self.valid=data['x'],data['y'],data['z'],data['valid']
        self.cell=float(self.x[1]-self.x[0])
        self.gx,self.gy=np.gradient(self.z,self.cell,self.cell)

    def sample(self, xy):
        xy=np.atleast_2d(xy)
        fx=(xy[:,0]-self.x[0])/self.cell
        fy=(xy[:,1]-self.y[0])/self.cell
        inside=(fx>=0)&(fy>=0)&(fx<len(self.x)-1)&(fy<len(self.y)-1)
        i=np.clip(np.floor(fx).astype(int),0,len(self.x)-2)
        j=np.clip(np.floor(fy).astype(int),0,len(self.y)-2)
        tx,ty=np.clip(fx-i,0,1),np.clip(fy-j,0,1)
        weights=[(1-tx)*(1-ty),tx*(1-ty),(1-tx)*ty,tx*ty]
        corners=[(i,j),(i+1,j),(i,j+1),(i+1,j+1)]
        valid=inside.copy()
        height=np.zeros(len(xy));gx=height.copy();gy=height.copy()
        for w,(a,b) in zip(weights,corners):
            valid &= self.valid[a,b]
            height+=w*self.z[a,b];gx+=w*self.gx[a,b];gy+=w*self.gy[a,b]
        normals=np.c_[-gx,-gy,np.ones(len(xy))]
        normals/=np.linalg.norm(normals,axis=1)[:,None]
        return height,normals,valid
