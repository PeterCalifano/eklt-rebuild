/// @file GtsamAliases.h
/// @brief Provides the minimal Eigen-backed aliases expected by gtwrap.
/// @details Co-located with the wrapper-adapter implementation, this header
///          preserves gtwrap's conventional matrix and vector spellings
///          without requiring GTSAM.

#ifndef WRAP_ADAPTERS_GTSAM_ALIASES_H_
#define WRAP_ADAPTERS_GTSAM_ALIASES_H_

#include <Eigen/Dense>

#if __has_include(<gtsam/base/Matrix.h>) && __has_include(<gtsam/base/Vector.h>)
#include <gtsam/base/Matrix.h>
#include <gtsam/base/Vector.h>
#else
namespace gtsam
{
    using Vector = Eigen::VectorXd;
    using Matrix = Eigen::MatrixXd;
} // namespace gtsam
#endif

#endif // WRAP_ADAPTERS_GTSAM_ALIASES_H_
