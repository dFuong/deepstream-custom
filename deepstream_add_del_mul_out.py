import argparse
import sys

sys.path.append('../')

import gi
import configparser
import random
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from datetime import datetime
from gi.repository import GObject, Gst, GstRtspServer
from common.is_aarch_64 import is_aarch64
from kafka import KafkaProducer
import json
# from common.bus_call import bus_call

import pyds
pipeline = None
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3


codec = "H264"
bitrate = 4000000
MAX_NUM_SOURCES = 2
GPU_ID = 0
rtsp_port_num = 8554

g_num_sources = 0
stream_path = [""] * MAX_NUM_SOURCES
g_source_id_list = [0] * MAX_NUM_SOURCES
g_eos_list = [False] * MAX_NUM_SOURCES
g_source_enabled = [False] * MAX_NUM_SOURCES
g_source_bin_list = [None] * MAX_NUM_SOURCES
check_add = [False] * MAX_NUM_SOURCES

nvanalytics = None
nvanalytics_config = {}
nvvidconv = [None] * MAX_NUM_SOURCES
nvosd = [None] * MAX_NUM_SOURCES
nvvidconv_postosd = [None] * MAX_NUM_SOURCES
caps = [None] * MAX_NUM_SOURCES
encoder = [None] * MAX_NUM_SOURCES
rtppay = [None] * MAX_NUM_SOURCES
sink = [None] * MAX_NUM_SOURCES
loop = None
pipeline = None
streammux = None
tracker = None
streamdemux = None
updsink_port_num = [5400, 5401]
factory = [None] * MAX_NUM_SOURCES
osdsinkpad = [None] * MAX_NUM_SOURCES
server = None
# streamdemux_pad = [None] * MAX_NUM_SOURCES

producer_0 = KafkaProducer(bootstrap_servers='192.168.1.29:9092', value_serializer=lambda v: json.dumps(v).encode('utf-8'))
producer_1 = KafkaProducer(bootstrap_servers='192.168.1.29:9092', value_serializer=lambda v: json.dumps(v).encode('utf-8'))
curTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def update_analytic_file(config_file):
    new_config = open("config_pipeline/config_nvdsanalytics_1.txt", "w")
    for element in config_file:
        new_config.writelines(config_file[element])

def edit_config_file(filename, source_id):
    read = open("./config_nvanalytics/" + filename.split(".")[0] + ".txt", "r").read().split("\n")
    new_sink = []
    for i, line in enumerate(read):
        if line == "":
            new_sink.append("\n")
            continue
        if line[0] == "[" and line[-2:] != "y]":
            new_sink.append(line[:-2] + str(source_id) + "]\n")
        else:
            new_sink.append(line + "\n")
    return new_sink

def osd_sink_pad_buffer_probe(pad, info, u_data):
    frame_number = 0
    # Intiallizing object counter with 0.
    obj_counter = {
        PGIE_CLASS_ID_VEHICLE: 0,
        PGIE_CLASS_ID_PERSON: 0,
        PGIE_CLASS_ID_BICYCLE: 0,
        PGIE_CLASS_ID_ROADSIGN: 0
    }
    num_rects = 0

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        frame_number = frame_meta.frame_num
        num_rects = frame_meta.num_obj_meta
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            obj_counter[obj_meta.class_id] += 1
            l_user_meta = obj_meta.obj_user_meta_list
            rect_para=obj_meta.rect_params
            frame_number=frame
            top_left=(rect_para.left, rect_para.top)
            bottom_left=(rect_para.left+1, rect_para.top +rect_para.height)
            top_right=(rect_para.left + rect_para.width, rect_para.top)
            bottom_right=(rect_para.left+rect_para.width +1, rect_para.top +rect_para.height)

            top = int(rect_para.top)
            left = int(rect_para.left)
            width = int(rect_para.width)
            height = int(rect_para.height)
            
            if (frame_meta.pad_index==0 and obj_meta.class_id==0 ):
                if (roi_poly.contains_point(top_left) or roi_poly.contains_point(top_right) or roi_poly.contains_point(bottom_right) or roi_poly.contains_point(bottom_left)):
                    print("\n----------------------Object in ROI {}------------------\n".format(frame_meta.pad_index))
                    print("Frame_number", frame_number)
                    print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                    producer_0.send('test',{'@timestamp':'{}'.format(curTime),'Object in ROI source-0':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
                
                
                if (roi_line.contains_point(top_left) or roi_line.contains_point(top_right) or roi_line.contains_point(bottom_right) or roi_line.contains_point(bottom_left)):
                    a_left=param_a(top_left, bottom_left)
                    a_right=param_a(top_right, bottom_right)
                    if ( a_init!=a_left or a_init!=a_right):
                        print("\n----------------------Object crossing Line {}------------------\n".format(frame_meta.pad_index))
                        print("Frame_number", frame_number)
                        print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                        producer_0.send('test',{'@timestamp':'{}'.format(curTime),'Object crossing Line source-0':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
            
            if (frame_meta.pad_index==1 and obj_meta.class_id==0 ):
                if (roi_poly_1.contains_point(top_left) or roi_poly_1.contains_point(top_right) or roi_poly_1.contains_point(bottom_right) or roi_poly_1.contains_point(bottom_left)):
                    print("\n----------------------Object in ROI {}------------------\n".format(frame_meta.pad_index))
                    print("Frame_number", frame_number)
                    print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                    producer_1.send('test1',{'@timestamp':'{}'.format(curTime),'Object in ROI source-1':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
                
                if (roi_line_1.contains_point(top_left) or roi_line_1.contains_point(top_right) or roi_line_1.contains_point(bottom_right) or roi_line_1.contains_point(bottom_left)):
                    a_left=param_a(top_left, bottom_left)
                    a_right=param_a(top_right, bottom_right)
                    if ( b_init!=a_left or b_init!=a_right):
                        print("\n----------------------Object crossing Line {}------------------\n".format(frame_meta.pad_index))
                        print("Frame_number", frame_number)
                        print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                        producer_1.send('test1',{'@timestamp':'{}'.format(curTime),'Object crossing Line source-1':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})                                              'height': '{}'.format(height)}}})
            try:
                l_obj = l_obj.next
            except StopIteration:
                break

        # Acquiring a display meta object. The memory ownership remains in
        # the C code so downstream plugins can still access it. Otherwise
        # the garbage collector will claim it when this probe function exits.
        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_labels = 1
        py_nvosd_text_params = display_meta.text_params[0]

        py_nvosd_text_params.display_text = "Frame Number={} Number of Objects={} Vehicle_count={} Person_count={}".format(
            frame_number, num_rects, obj_counter[PGIE_CLASS_ID_VEHICLE], obj_counter[PGIE_CLASS_ID_PERSON])

        # Now set the offsets where the string should appear
        py_nvosd_text_params.x_offset = 10
        py_nvosd_text_params.y_offset = 12

        # Font , font-color and font-size
        py_nvosd_text_params.font_params.font_name = "Serif"
        py_nvosd_text_params.font_params.font_size = 10
        # set(red, green, blue, alpha); set to White
        py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

        # Text background color
        py_nvosd_text_params.set_bg_clr = 1
        # set(red, green, blue, alpha); set to Black
        py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)

        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK
    
def decodebin_child_added(child_proxy, Object, name, user_data):
    print("Decodebin child added:", name, "\n")
    if (name.find("decodebin") != -1):
        Object.connect("child-added", decodebin_child_added, user_data)
    if (name.find("nvv4l2decoder") != -1):
        if (is_aarch64()):
            Object.set_property("enable-max-performance", True)
            Object.set_property("drop-frame-interval", 0)
            Object.set_property("num-extra-surfaces", 0)
        else:
            Object.set_property("gpu_id", GPU_ID)

def cb_newpad(decodebin, pad, data):
    global streammux
    print("In cb_newpad\n")
    caps = pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    print("gstname=", gstname)
    if (gstname.find("video") != -1):
        source_id = data
        pad_name = "sink_%u" % source_id
        print(pad_name)
        # Get a sink pad from the streammux, link to decodebin
        sinkpad = streammux.get_request_pad(pad_name)
        if pad.link(sinkpad) == Gst.PadLinkReturn.OK:
            print("Decodebin linked to pipeline")
        else:
            sys.stderr.write("Failed to link decodebin to pipeline\n")


def create_uridecode_bin(index, filename):
    global g_source_id_list
    print("Creating uridecodebin for [%s]" % filename)

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    g_source_id_list[index] = index
    bin_name = "source-bin-%02d" % index
    print(bin_name)

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
    bin = Gst.ElementFactory.make("uridecodebin", bin_name)
    if not bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    # We set the input uri to the source element
    bin.set_property("uri", filename)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has been created by the decodebin
    bin.connect("pad-added", cb_newpad, g_source_id_list[index])
    bin.connect("child-added", decodebin_child_added, g_source_id_list[index])

    # Set status of the source to enabled
    g_source_enabled[index] = True

    return bin


def stop_release_source(source_id):
    global g_num_sources
    global g_source_bin_list
    global streammux
    global pipeline

    # Attempt to change status of source to be released
    state_return = g_source_bin_list[source_id].set_state(Gst.State.NULL)

    if state_return == Gst.StateChangeReturn.SUCCESS:
        print("STATE CHANGE SUCCESS\n")
        pad_name = "sink_%u" % source_id
        print(pad_name)
        # Retrieve sink pad to be released
        sinkpad = streammux.get_static_pad(pad_name)
        # Send flush stop event to the sink pad, then release from the streammux
        sinkpad.send_event(Gst.Event.new_flush_stop(False))
        streammux.release_request_pad(sinkpad)
        print("STATE CHANGE SUCCESS\n")
        # Remove the source bin from the pipeline
        pipeline.remove(g_source_bin_list[source_id])
        source_id -= 1
        g_num_sources -= 1

    elif state_return == Gst.StateChangeReturn.FAILURE:
        print("STATE CHANGE FAILURE\n")

    elif state_return == Gst.StateChangeReturn.ASYNC:
        state_return = g_source_bin_list[source_id].get_state(Gst.CLOCK_TIME_NONE)
        pad_name = "sink_%u" % source_id
        print(pad_name)
        sinkpad = streammux.get_static_pad(pad_name)
        sinkpad.send_event(Gst.Event.new_flush_stop(False))
        streammux.release_request_pad(sinkpad)
        print("STATE CHANGE ASYNC\n")
        pipeline.remove(g_source_bin_list[source_id])
        source_id -= 1
        g_num_sources -= 1


def delete_sources(data):
    global loop
    global g_num_sources
    global g_eos_list
    global g_source_enabled

    # First delete sources that have reached end of stream
    for source_id in range(MAX_NUM_SOURCES):
        if (g_eos_list[source_id] and g_source_enabled[source_id]):
            g_source_enabled[source_id] = False
            stop_release_source(source_id)

    # Quit if no sources remaining
    if (g_num_sources == 0):
        loop.quit()
        print("All sources stopped quitting")
        return False
    print("Enter id to delete:")
    source_id = int(input())
    stream_path[source_id] = ""
 
    g_source_enabled[source_id] = False
    # Release the source
    print("Calling Stop %d " % source_id)
    stop_release_source(source_id)

    # Quit if no sources remaining
    if (g_num_sources == 0):
        loop.quit()
        print("All sources stopped quitting")
        return False
    print("In delete_source: Deleted")
    return False


def add_sources(data):
    global g_num_sources
    global g_source_enabled
    global streamdemux
    global pipeline
    global streammux
    global server
    global factory
    global osdsinkpad
    # global streamdemux_pad
    global check_add
    global nvanalytics_config
    global nvanalytics
    # global g_source_bin_list

    # # Randomly select an un-enabled source to add
    # source_id = random.randrange(0, MAX_NUM_SOURCES)
    # while (g_source_enabled[source_id]):
    #     source_id = random.randrange(0, MAX_NUM_SOURCES)
    print("New loop")
    # print("nvnanalytics:", nvanalytics)
    print("Choose: a. Add | b. Delete")
    s = input()
    if s == "a":
        print("Enter new id:")
        source_id = int(input())
        print("Enter new source:")
        uri = input()

        # Enable the source
        g_source_enabled[source_id] = True

        print("Calling Start %d " % source_id)

        # Create a uridecode bin with the chosen source id
        source_bin = create_uridecode_bin(source_id, uri)

        if (not source_bin):
            sys.stderr.write("Failed to create source bin. Exiting.")
            exit(1)

        # Add source bin to our list and to pipeline
        g_source_bin_list[source_id] = source_bin
        pipeline.add(source_bin)

        g_num_sources += 1
        stream_path[source_id] = uri
        video_name = stream_path[source_id].split("/")[-1]
        nvanalytics_config["sink" + str(source_id)] = edit_config_file(video_name, source_id)
        update_analytic_file(nvanalytics_config)
        nvanalytics.set_property("config-file", "config_nvdsanalytics.txt")
        # Set state of source bin to playing
        state_return = g_source_bin_list[source_id].set_state(Gst.State.PLAYING)

        if state_return == Gst.StateChangeReturn.SUCCESS:
            print("STATE CHANGE SUCCESS\n")
            # source_id += 1

        elif state_return == Gst.StateChangeReturn.FAILURE:
            print("STATE CHANGE FAILURE\n")

        elif state_return == Gst.StateChangeReturn.ASYNC:
            state_return = g_source_bin_list[source_id].get_state(Gst.CLOCK_TIME_NONE)
            # source_id += 1

        elif state_return == Gst.StateChangeReturn.NO_PREROLL:
            print("STATE CHANGE NO PREROLL\n")
        print("In add_source: Added")
        return True
    elif s == "b":
        GObject.timeout_add_seconds(0, delete_sources, g_source_bin_list)
        print("In add_source: Deleted")
        return True

    else:
        print("In add_source: Skipped")
        return True


def bus_call(bus, message, loop):
    global g_eos_list
    t = message.type
    if t == Gst.MessageType.EOS:
        sys.stdout.write("End-of-stream\n")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n" % (err, debug))
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        sys.stderr.write("Error: %s: %s\n" % (err, debug))
        loop.quit()
    elif t == Gst.MessageType.ELEMENT:
        struct = message.get_structure()
        # Check for stream-eos message
        if struct is not None and struct.has_name("stream-eos"):
            parsed, stream_id = struct.get_uint("stream-id")
            if parsed:
                # Set eos status of stream to True, to be deleted in delete-sources
                print("Got EOS from stream %d" % stream_id)
                g_eos_list[stream_id] = True
    return True

def main(args):
    global g_num_sources
    global g_source_bin_list

    global loop
    global pipeline
    global streammux
    global streamdemux
    global sink
    global pgie
    global nvvidconv
    global nvvidconv_postosd
    global nvanalytics
    global nvosd
    global caps
    global encoder
    global rtppay
    global tracker
    global updsink_port_num
    global factory
    global osdsinkpad
    global server
    # global streamdemux_pad
    global check_add
    global nvanalytics_config
    # Standard GStreamer initialization
    GObject.threads_init()
    Gst.init(None)

    num_sources = 1
    # Create gstreamer elements
    # Create Pipeline element that will form a connection of other elements
    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")

    # Create nvstreammux instance to form batches from one or more sources.
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

    pipeline.add(streammux)

    streamdemux = Gst.ElementFactory.make("nvstreamdemux", "Stream-demuxer")
    if not streamdemux:
        sys.stderr.write(" Unable to create NvStreamdeMux \n")
    # streamdemux.set_property("batch-size", MAX_NUM_SOURCES)

    streammux.set_property("live-source", 1)
    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', MAX_NUM_SOURCES)
    streammux.set_property('batched-push-timeout', 4000000)
    print("Enter the source id (int):")
    source_id = int(input())
    print("Enter the input source:")
    uri_name = input()
    print("Source_id:", source_id, "Input_source:", uri_name)
    stream_path[source_id] = uri_name
    g_num_sources += 1
    if uri_name.find("rtsp://") == 0:
        is_live = True
    # Create first source bin and add to pipeline
    source_bin = create_uridecode_bin(source_id, uri_name)
    if not source_bin:
        sys.stderr.write("Failed to create source bin. Exiting. \n")
        sys.exit(1)
    g_source_bin_list[source_id] = source_bin
    pipeline.add(source_bin)
    check_add[source_id] = True

    # Use nvinfer to run inferencing on decoder's output,
    # behaviour of inferencing is set through config file
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie \n")

    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    if not tracker:
        sys.stderr.write(" Unable to create tracker \n")

    # Set properties of tracker
    config = configparser.ConfigParser()
    config.read('config_tracker/dstest_tracker_config.txt')
    config.sections()

    for key in config['tracker']:
        if key == 'tracker-width':
            tracker_width = config.getint('tracker', key)
            tracker.set_property('tracker-width', tracker_width)
        if key == 'tracker-height':
            tracker_height = config.getint('tracker', key)
            tracker.set_property('tracker-height', tracker_height)
        if key == 'gpu-id':
            tracker_gpu_id = config.getint('tracker', key)
            tracker.set_property('gpu_id', tracker_gpu_id)
        if key == 'll-lib-file':
            tracker_ll_lib_file = config.get('tracker', key)
            tracker.set_property('ll-lib-file', tracker_ll_lib_file)
        if key == 'll-config-file':
            tracker_ll_config_file = config.get('tracker', key)
            tracker.set_property('ll-config-file', tracker_ll_config_file)
        if key == 'enable-batch-process':
            tracker_enable_batch_process = config.getint('tracker', key)
            tracker.set_property('enable_batch_process', tracker_enable_batch_process)
        if key == 'enable-past-frame':
            tracker_enable_past_frame = config.getint('tracker', key)
            tracker.set_property('enable_past_frame', tracker_enable_past_frame)

    nvanalytics = Gst.ElementFactory.make("nvdsanalytics", "analytics")
    if not nvanalytics:
        sys.stderr.write(" Unable to create nvanalytics \n")
    f = open("config_pipeline/property.txt", "r").read().split("\n")
    property_config = []
    for i, line in enumerate(f):
        property_config.append(line + "\n")
    nvanalytics_config["property"]  = property_config
    # update_analytic_file(nvanalytics_config)
    for i in range(0, MAX_NUM_SOURCES):
        # Use convertor to convert from NV12 to RGBA as required by nvosd
        nvvidconv[i] = Gst.ElementFactory.make("nvvideoconvert", "convertor" + str(i))
        if not nvvidconv[i]:
            sys.stderr.write(" Unable to create nvvidconv \n")
        pipeline.add(nvvidconv[i])
        # Create OSD to draw on the converted RGBA buffer
        nvosd[i] = Gst.ElementFactory.make("nvdsosd", "onscreendisplay" + str(i))
        if not nvosd[i]:
            sys.stderr.write(" Unable to create nvosd \n")
        pipeline.add(nvosd[i])

        # nvanalytics[i] = Gst.ElementFactory.make("nvdsanalytics", "analytics" + str(i))
        # if not nvanalytics:
        #     sys.stderr.write(" Unable to create nvanalytics \n")
        # nvanalytics[i].set_property("config-file", "config_nvdsanalytics.txt")
        # pipeline.add(nvanalytics[i])

        nvvidconv_postosd[i] = Gst.ElementFactory.make("nvvideoconvert", "convertor_postosd" + str(i))
        if not nvvidconv_postosd[i]:
            sys.stderr.write(" Unable to create nvvidconv_postosd \n")
        pipeline.add(nvvidconv_postosd[i])

        # Create a caps filter
        caps[i] = Gst.ElementFactory.make("capsfilter", "filter" + str(i))
        caps[i].set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))
        pipeline.add(caps[i])

        # Make the encoder
        if codec == "H264":
            encoder[i] = Gst.ElementFactory.make("nvv4l2h264enc", "encoder" + str(i))
            print("Creating H264 Encoder")
        elif codec == "H265":
            encoder[i] = Gst.ElementFactory.make("nvv4l2h265enc", "encoder" + str(i))
            print("Creating H265 Encoder")
        if not encoder[i]:
            sys.stderr.write(" Unable to create encoder")
        encoder[i].set_property('bitrate', bitrate)
        if is_aarch64():
            encoder[i].set_property('preset-level', 1)
            encoder[i].set_property('insert-sps-pps', 1)
            encoder[i].set_property('bufapi-version', 1)
        pipeline.add(encoder[i])

        # Make the payload-encode video into RTP packets
        if codec == "H264":
            rtppay[i] = Gst.ElementFactory.make("rtph264pay", "rtppay" + str(i))
            print("Creating H264 rtppay")
        elif codec == "H265":
            rtppay[i] = Gst.ElementFactory.make("rtph265pay", "rtppay" + str(i))
            print("Creating H265 rtppay")
        if not rtppay[i]:
            sys.stderr.write(" Unable to create rtppay")
        pipeline.add(rtppay[i])

        # Make the UDP sink
        sink[i] = Gst.ElementFactory.make("udpsink", "udpsink" + str(i))
        if not sink[i]:
            sys.stderr.write(" Unable to create udpsink")

        sink[i].set_property('host', '127.0.0.1')
        sink[i].set_property('port', updsink_port_num[i])
        sink[i].set_property('async', False)
        sink[i].set_property('sync', 1)
        pipeline.add(sink[i])

    video_name = stream_path[source_id].split("/")[-1]
    nvanalytics_config["sink" + str(source_id)] = edit_config_file(video_name, source_id)
    update_analytic_file(nvanalytics_config)
    nvanalytics.set_property("config-file", "config_nvdsanalytics.txt")
    pipeline.add(nvanalytics)
    is_live = 0
    if is_live:
        print("Atleast one of the sources is live")
        streammux.set_property('live-source', 1)
    print("Playing file %s " % stream_path)
    # source.set_property('location', stream_path)
    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)

    pgie.set_property('config-file-path', "dsnvanalytics_pgie_config.txt")
    print("Adding elements to Pipeline \n")

    pipeline.add(pgie)
    pipeline.add(streamdemux)
    pipeline.add(tracker)

    # Link the elements together:
    # file-source -> h264-parser -> nvh264-decoder ->
    # nvinfer -> nvvidconv -> nvosd -> nvvidconv_postosd ->
    # caps -> encoder -> rtppay -> udpsink

    print("Linking elements in the Pipeline \n")
    """
    source.link(h264parser)
    h264parser.link(decoder)
    sinkpad = streammux.get_request_pad("sink_0")
    if not sinkpad:
        sys.stderr.write(" Unable to get the sink pad of streammux \n")

    srcpad = decoder.get_static_pad("src")
    if not srcpad:
        sys.stderr.write(" Unable to get source pad of decoder \n")

    srcpad.link(sinkpad)
    """
    streammux.link(pgie)
    # pgie.link(nvvidconv)
    pgie.link(tracker)
    tracker.link(nvanalytics)
    nvanalytics.link(streamdemux)
    #######################
    for i in range(0, MAX_NUM_SOURCES):
        print("demux source", i, "\n")
        # if stream_path[i] == "": continue
        srcpad1 = streamdemux.get_request_pad("src_%u" % i)
        if not srcpad1:
            sys.stderr.write(" Unable to get the src pad of streamdemux \n")
        sinkpad1 = nvvidconv[i].get_static_pad("sink")
        if not sinkpad1:
            sys.stderr.write(" Unable to get sink pad of nvvidconv \n")
        srcpad1.link(sinkpad1)
        #######################
        nvvidconv[i].link(nvosd[i])
        nvosd[i].link(nvvidconv_postosd[i])
        nvvidconv_postosd[i].link(caps[i])
        caps[i].link(encoder[i])
        encoder[i].link(rtppay[i])
        rtppay[i].link(sink[i])

    # create an event loop and feed gstreamer bus mesages to it
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    # Start streaming

    server = GstRtspServer.RTSPServer.new()
    server.props.service = "%d" % rtsp_port_num
    server.attach(None)

    for i in range(0, MAX_NUM_SOURCES):
        factory[i] = GstRtspServer.RTSPMediaFactory.new()
        factory[i].set_launch(
            "( udpsrc name=pay0 port=%d buffer-size=524288 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 \" )" % (
            updsink_port_num[i], codec))
        factory[i].set_shared(True)
        server.get_mount_points().add_factory("/ds-test" + str(i + 1), factory[i])

        print("\n *** DeepStream: Launched RTSP Streaming at rtsp://localhost:%d/ds-test ***\n\n" % rtsp_port_num)

        # Lets add probe to get informed of the meta data generated, we add probe to
        # the sink pad of the osd element, since by that time, the buffer would have
        # had got all the metadata.
        osdsinkpad[i] = nvosd[i].get_static_pad("sink")
        if not osdsinkpad[i]:
            sys.stderr.write(" Unable to get sink pad of nvosd \n")

        osdsinkpad[i].add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # start play back and listen to events
    print("Starting pipeline \n")
    pipeline.set_state(Gst.State.PLAYING)
    GObject.timeout_add_seconds(15, add_sources, g_source_bin_list)
    try:
        loop.run()
    except:
        pass
    # cleanup
    pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    # parse_args()
    sys.exit(main(sys.argv))

