class RasterizeCudaContext:
    def __init__(self,*a,**k): pass
class RasterizeGLContext:
    def __init__(self,*a,**k): pass
def _stub(*a,**k): raise RuntimeError("nvdiffrast stub (mesh export uses PyMCubes; rasterization not available)")
rasterize=_stub; interpolate=_stub; texture=_stub; antialias=_stub
