// blip-analysis-wrapper.cpp
// C++ FFI wrapper for robust blip analysis along 1D ray traces in gate voltage space.

#include <algorithm>
#include <cmath>
#include <falcon-typing/FFIHelpers.hpp>
#include <falcon-core/generic/FArray.hpp>
#include <falcon-core/math/Point.hpp>
#include <falcon-core/math/Quantity.hpp>
#include <falcon-core/math/arrays/LabelledMeasuredArray.hpp>
#include <falcon-core/physics/device_structures/Connection.hpp>
#include <falcon-core/physics/units/SymbolUnit.hpp>
#include <memory>
#include <spdlog/spdlog.h>
#include <stdexcept>
#include <string>
#include <vector>

using namespace falcon::typing;
using namespace falcon::typing::ffi::wrapper;

using Point = falcon_core::math::Point;
using PointSP = std::shared_ptr<Point>;
using Quantity = falcon_core::math::Quantity;
using QuantitySP = std::shared_ptr<Quantity>;
using Connection = falcon_core::physics::device_structures::Connection;
using ConnectionSP = std::shared_ptr<Connection>;
using SymbolUnit = falcon_core::physics::units::SymbolUnit;
using SymbolUnitSP = std::shared_ptr<SymbolUnit>;
using FArray = falcon_core::generic::FArray<double>;
using FArraySP = std::shared_ptr<FArray>;
using LabelledMeasuredArray = falcon_core::math::arrays::LabelledMeasuredArray;
using LabelledMeasuredArraySP = std::shared_ptr<LabelledMeasuredArray>;

namespace {

// Robust peak detection algorithm for 1D blips / coulomb blockade oscillations
std::vector<int> detect_blip_peaks(const std::vector<double> &signal,
                                   double threshold_sigma) {
  const int n = static_cast<int>(signal.size());
  if (n < 3) {
    return {};
  }

  // Work with absolute differentiated signal or magnitude
  std::vector<double> abs_signal(n);
  for (int i = 0; i < n; ++i) {
    abs_signal[i] = std::abs(signal[i]);
  }

  double sum = 0.0;
  for (double val : abs_signal) {
    sum += val;
  }
  double mean = sum / n;

  double sq_sum = 0.0;
  for (double val : abs_signal) {
    sq_sum += (val - mean) * (val - mean);
  }
  double stddev = std::sqrt(sq_sum / n);
  double threshold = mean + (threshold_sigma * stddev);

  std::vector<int> peaks;
  int i = 1;
  while (i < n - 1) {
    // Local maximum condition above threshold
    if (abs_signal[i] >= abs_signal[i - 1] &&
        abs_signal[i] >= abs_signal[i + 1] &&
        abs_signal[i] > threshold) {
      int plateau_start = i;
      int plateau_end = i;
      while (plateau_end + 1 < n - 1 &&
             abs_signal[plateau_end] == abs_signal[plateau_end + 1]) {
        ++plateau_end;
      }
      // Use the center of the plateau
      int peak_idx = (plateau_start + plateau_end) / 2;
      peaks.push_back(peak_idx);
      i = plateau_end + 1;
    } else {
      ++i;
    }
  }

  return peaks;
}

// Convert peak indices along 1D ray [0, n-1] into Point objects interpolated
// between startPoint and endPoint.
std::vector<PointSP> compute_blip_points(const std::vector<int> &peak_indices,
                                         int total_points,
                                         const PointSP &start_point,
                                         const PointSP &end_point) {
  std::vector<PointSP> blips;
  blips.reserve(peak_indices.size());

  auto volt_unit = SymbolUnit::Volt();
  auto start_map = start_point->coordinates();
  auto end_map = end_point->coordinates();

  for (int peak_idx : peak_indices) {
    double frac = 0.0;
    if (total_points > 1) {
      frac = static_cast<double>(peak_idx) / static_cast<double>(total_points - 1);
    }

    auto pt = std::make_shared<Point>();
    for (const auto &conn : start_point->connections()->items()) {
      double v_start = 0.0;
      double v_end = 0.0;

      if (start_map->contains(conn)) {
        auto q = start_map->at(conn);
        auto q_copy = std::make_shared<Quantity>(*q);
        q_copy->convert_to(volt_unit);
        v_start = q_copy->value();
      }
      if (end_map->contains(conn)) {
        auto q = end_map->at(conn);
        auto q_copy = std::make_shared<Quantity>(*q);
        q_copy->convert_to(volt_unit);
        v_end = q_copy->value();
      }

      double v_blip = v_start + (v_end - v_start) * frac;
      pt->insert(conn, std::make_shared<Quantity>(v_blip, volt_unit));
    }
    blips.push_back(pt);
  }

  return blips;
}

static void pack_point_array(std::vector<PointSP> points,
                             FalconResultSlot *out, int32_t *oc) {
  auto arr = std::make_shared<ArrayValue>("Point");
  arr->elements.reserve(points.size());
  for (auto &pt : points) {
    auto inst = std::make_shared<StructInstance>("Point");
    inst->native_handle = std::static_pointer_cast<void>(pt);
    arr->elements.push_back(std::move(inst));
  }

  out[0] = {};
  out[0].tag = FALCON_TYPE_OPAQUE;
  out[0].value.opaque.type_name = "Array";
  out[0].value.opaque.ptr =
      new std::shared_ptr<void>(std::static_pointer_cast<void>(arr));
  out[0].value.opaque.deleter = [](void *p) {
    delete static_cast<std::shared_ptr<void> *>(p);
  };
  *oc = 1;
}

static PointSP get_point_param(const ParameterMap &pm, const std::string &key) {
  auto it = pm.find(key);
  if (it == pm.end()) {
    throw std::runtime_error("Parameter '" + key + "' not found");
  }
  if (!std::holds_alternative<std::shared_ptr<StructInstance>>(it->second)) {
    throw std::runtime_error("Parameter '" + key + "' is not a StructInstance");
  }
  auto inst = std::get<std::shared_ptr<StructInstance>>(it->second);
  if (!inst || !inst->native_handle.has_value()) {
    throw std::runtime_error("Parameter '" + key + "' has no native handle");
  }
  return std::static_pointer_cast<Point>(inst->native_handle.value());
}

} // namespace

extern "C" {

void AnalyzeRayBlips(const FalconParamEntry *params, int32_t param_count,
                     FalconResultSlot *out, int32_t *oc) {
  auto pm = unpack_params(params, param_count);

  auto it_trace = pm.find("trace");
  if (it_trace == pm.end()) {
    throw std::runtime_error("AnalyzeRayBlips: 'trace' param not found");
  }
  auto trace_inst = std::get<std::shared_ptr<StructInstance>>(it_trace->second);
  auto lma = std::static_pointer_cast<LabelledMeasuredArray>(trace_inst->native_handle.value());

  auto start_point = get_point_param(pm, "startPoint");
  auto end_point = get_point_param(pm, "endPoint");

  double threshold_sigma = 2.0;
  auto it_thresh = pm.find("thresholdSigma");
  if (it_thresh != pm.end()) {
    if (std::holds_alternative<double>(it_thresh->second)) {
      threshold_sigma = std::get<double>(it_thresh->second);
    } else if (std::holds_alternative<int64_t>(it_thresh->second)) {
      threshold_sigma = static_cast<double>(std::get<int64_t>(it_thresh->second));
    }
  }

  // Extract raw signal from LabelledMeasuredArray
  // LabelledMeasuredArray inherits from MeasuredArray which wraps FArray<double>
  const auto &farray_data = lma->data();
  std::vector<double> signal(farray_data.begin(), farray_data.end());

  auto peak_indices = detect_blip_peaks(signal, threshold_sigma);
  spdlog::info("AnalyzeRayBlips: detected {} peaks along ray trace of size {}",
               peak_indices.size(), signal.size());

  auto blip_points = compute_blip_points(peak_indices, static_cast<int>(signal.size()),
                                         start_point, end_point);

  pack_point_array(std::move(blip_points), out, oc);
}

void AnalyzeFArrayRayBlips(const FalconParamEntry *params, int32_t param_count,
                           FalconResultSlot *out, int32_t *oc) {
  auto pm = unpack_params(params, param_count);

  auto it_trace = pm.find("trace");
  if (it_trace == pm.end()) {
    throw std::runtime_error("AnalyzeFArrayRayBlips: 'trace' param not found");
  }
  auto trace_inst = std::get<std::shared_ptr<StructInstance>>(it_trace->second);
  auto farr = std::static_pointer_cast<FArray>(trace_inst->native_handle.value());

  auto start_point = get_point_param(pm, "startPoint");
  auto end_point = get_point_param(pm, "endPoint");

  double threshold_sigma = 2.0;
  auto it_thresh = pm.find("thresholdSigma");
  if (it_thresh != pm.end()) {
    if (std::holds_alternative<double>(it_thresh->second)) {
      threshold_sigma = std::get<double>(it_thresh->second);
    } else if (std::holds_alternative<int64_t>(it_thresh->second)) {
      threshold_sigma = static_cast<double>(std::get<int64_t>(it_thresh->second));
    }
  }

  const auto &farray_data = farr->data();
  std::vector<double> signal(farray_data.begin(), farray_data.end());

  auto peak_indices = detect_blip_peaks(signal, threshold_sigma);
  spdlog::info("AnalyzeFArrayRayBlips: detected {} peaks along ray trace of size {}",
               peak_indices.size(), signal.size());

  auto blip_points = compute_blip_points(peak_indices, static_cast<int>(signal.size()),
                                         start_point, end_point);

  pack_point_array(std::move(blip_points), out, oc);
}

} // extern "C"
