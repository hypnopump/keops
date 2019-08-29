#pragma once

#include <sstream>

#include "core/Pack.h"
#include "core/autodiff.h"
#include "core/formulas/constants.h"
#include "core/formulas/maths/Mult.h"
#include "core/formulas/maths/Scal.h"


namespace keops {


//////////////////////////////////////////////////////////////
////             SQUARED OPERATOR : Square< F >           ////
//////////////////////////////////////////////////////////////

//template < class F >
//using Square = Pow<F,2>;

template<class F>
struct Square : UnaryOp<Square, F> {

  static const int DIM = F::DIM;

  static void PrintIdString(std::stringstream &str) {
    str << "Sq";
  }

  static HOST_DEVICE INLINE void Operation(__TYPE__ *out, __TYPE__ *outF) {
#pragma unroll
    for (int k = 0; k < DIM; k++) {
      __TYPE__ temp = outF[k];
      out[k] = temp * temp;
    }
  }

  template<class V, class GRADIN>
  using DiffTF = typename F::template DiffT<V, GRADIN>;

  // [\partial_V (F)**2].gradin = F * [\partial_V F].gradin
  template<class V, class GRADIN>
  using DiffT = Scal<IntConstant<2>, DiffTF<V, Mult<F, GRADIN>>>;

};
}