from keops.python_engine.formulas.Operation import Operation
from keops.python_engine.utils.code_gen_utils import c_for_loop

#/////////////////////////////////////////////////////////////////////////
#////      adjoint of ComplexSum                           ////
#/////////////////////////////////////////////////////////////////////////

class ComplexSumT(Operation):
    string_id = "ComplexSumT"

    def __init__(self, f, dim):
        if f.dim != 2:
            raise ValueError("Dimension of F must be 2")
        self.dim = dim
        super().__init__(f)
    
    def Op(self, out, table, inF):
        forloop, i = c_for_loop(0, self.dim, 2, pragma_unroll=True)
        body = out[i].assign( inF[0] )
        body += out[i+1].assign( inF[1] )
        return forloop(body)

    def DiffT(self, v, gradin):
        from keops.python_engine.formulas.complex.ComplexSum import ComplexSum
        f = self.children[0]
        return f.DiffT(v, ComplexSum(gradin))
