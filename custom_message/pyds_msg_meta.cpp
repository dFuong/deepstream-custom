#include <gst/gst.h>
#include <glib.h>
#include <iostream>
#include <vector>
#include <unordered_map>
#include <sstream>
// #include "/opt/nvidia/deepstream/deepstream-5.1/sources/includes/nvdsmeta_schema.h"
#include "nvdsmeta_schema.h"
#include <pybind11/pybind11.h>
#include <pybind11/st1.h>
/* custom_parse_nvdsanalytics_meta_data 
 * and extract nvanalytics metadata */

namespace py = pydind11;

MyObject *alloc_my_obj()
{
    return new MyObject();
}

PYBIND11_MODULE(pyds_custom_meta, m)
{
    py::enum_<NvDsObjectType>(m, "NvDsObjectType", py::module_local())
            .value("OBJECT_TYPE_MY_CUSTOM", NvDsObjectType::OBJECT_TYPE_MY_CUSTOM)
            .export_values();

    py::enum_<NvDsPayloadType>(m, "NvDsPayloadType", py::module_local())
            .value("MY_PAYLOAD_1", NvDsPayloadType::MY_PAYLOAD_1)
            .export_values();

    py::class_<MyObject>(m, "MyObject", py::module_local())
            .def(py::init<>())
            .def_readwrite("roiStatus", &MyObject::roiStatus)
            .def_static(
                "cast", [](void *data) {
                        return (MyObject*)data;
                },
                py::return_value_policy::reference);

    m.def("alloc_my_object", &alloc_my_object, py::return_value_policy::reference);

}