/// @file GtsamAliases.h
/// @brief Provides the minimal Eigen-backed aliases expected by gtwrap.
/// @details EKLT does not require GTSAM; these aliases preserve gtwrap's
///          conventional matrix and vector spellings at the wrapper boundary.

#ifndef EVENT_RECON_FIBAR_ADAPTERS_GTSAM_ALIASES_H_
#define EVENT_RECON_FIBAR_ADAPTERS_GTSAM_ALIASES_H_

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

#endif // EVENT_RECON_FIBAR_ADAPTERS_GTSAM_ALIASES_H_
