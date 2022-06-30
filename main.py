import os

import cv2
import numpy as np

from cv_bridge import CvBridge
import rospy
from sensor_msgs.msg import Image

# Constants.
INPUT_WIDTH = 320
INPUT_HEIGHT = 320
SCORE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.1
CONFIDENCE_THRESHOLD = 0.4

# Text parameters.
FONT_FACE = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.7
THICKNESS = 1

# Colors.
BLACK = (0, 0, 0)
BLUE = (255, 178, 50)
YELLOW = (0, 255, 255)

ros_image = None
bridge = CvBridge()

def callback(message):
    global ros_image
    ros_image = cv2.cvtColor(bridge.imgmsg_to_cv2(message, desired_encoding='passthrough'), cv2.COLOR_BGR2RGB)

def draw_label(im, label, x, y):
    """Draw text onto image at location."""
    # Get text size.
    text_size = cv2.getTextSize(label, FONT_FACE, FONT_SCALE, THICKNESS)
    dim, baseline = text_size[0], text_size[1]
    # Use text size to create a BLACK rectangle.
    cv2.rectangle(im, (x, y), (x + dim[0], y + dim[1] + baseline), (0, 0, 0), cv2.FILLED);
    # Display text inside the rectangle.
    cv2.putText(im, label, (x, y + dim[1]), FONT_FACE, FONT_SCALE, YELLOW, THICKNESS, cv2.LINE_AA)


def pre_process(input_image, net):
    # Create a 4D blob from a frame.
    blob = cv2.dnn.blobFromImage(input_image, 1 / 255, (INPUT_WIDTH, INPUT_HEIGHT), [0, 0, 0], 1, crop=False)

    # Sets the input to the network.
    net.setInput(blob)

    # Run the forward pass to get output of the output layers.
    outputs = net.forward(net.getUnconnectedOutLayersNames())
    return outputs


def post_process(input_image, outputs, draw=False):
    # Lists to hold respective values while unwrapping.
    class_ids = []
    confidences = []
    boxes = []
    # Rows.
    rows = outputs[0].shape[1]
    image_height, image_width = input_image.shape[:2]
    # Resizing factor.
    x_factor = image_width / INPUT_WIDTH
    y_factor = image_height / INPUT_HEIGHT
    # Iterate through detections.
    for r in range(rows):
        row = outputs[0][0][r]
        confidence = row[4]
        # Discard bad detections and continue.
        if confidence >= CONFIDENCE_THRESHOLD:
            classes_scores = row[5:]
            # Get the index of max class score.
            class_id = np.argmax(classes_scores)
            #  Continue if the class score is above threshold.
            if (classes_scores[class_id] > SCORE_THRESHOLD):
                confidences.append(confidence)
                class_ids.append(class_id)
                cx, cy, w, h = row[0], row[1], row[2], row[3]
                left = int((cx - w / 2) * x_factor)
                top = int((cy - h / 2) * y_factor)
                width = int(w * x_factor)
                height = int(h * y_factor)
                box = np.array([left, top, width, height])
                boxes.append(box)
                # Perform non maximum suppression to eliminate redundant, overlapping boxes with lower confidences.
    indices = cv2.dnn.NMSBoxes(boxes, confidences, CONFIDENCE_THRESHOLD, NMS_THRESHOLD)

    if draw:
        for i in indices:
            box = boxes[i]
            left = box[0]
            top = box[1]
            width = box[2]
            height = box[3]
            # Draw bounding box.
            cv2.rectangle(input_image, (left, top), (left + width, top + height), BLUE, 3 * THICKNESS)
            # Class label.
            label = "{}:{:.2f}".format(classes[class_ids[i]], confidences[i])
            # Draw label.
            draw_label(input_image, label, left, top - 30)
    else:
        input_image = None
    if not len(indices):
        return input_image, [], 0
    else:
        index = np.argmax(confidences)
        return input_image, boxes[index], confidences[index]


if __name__ == '__main__':
    rospy.init_node("drone_detection")
    draw = True
    
    # capture = cv2.VideoCapture(0)
    bridge = CvBridge()
    # capture.set(3, 640)
    # capture.set(4, 480)
    topic = rospy.Publisher("camera/color/drone_detection", Image, queue_size=10)
    rospy.Subscriber("/camera/color/image_raw", Image, callback)

    modelWeights = "weights.onnx"
    net = cv2.dnn.readNet(modelWeights)
    print("Net initialized")

    # Load class names.
    classesFile = "classes.txt"
    with open(classesFile, 'rt') as f:
        classes = f.read().rstrip('\n').split('\n')

    images_dir = './test/images/'
    # for image in os.listdir(images_dir):
    while True:
        # image_path = os.path.join(images_dir, image)
        # Load image.
        # frame = cv2.imread(image_path)
        # success, frame = capture.read()
        frame = ros_image
        if frame is None:
            print("NULL FRAME")
            continue
        print("New frame")
        # Give the weight files to the model and load the network using       them.
        # Process image.
        detections = pre_process(frame, net)
        img, boxes, confidences = post_process(frame.copy(), detections, draw=draw)
        print(boxes)
        """
        Put efficiency information. The function getPerfProfile returns       the overall time for inference(t)
        and the timings for each of the layers(in layersTimes).
        """
        t, _ = net.getPerfProfile()
        label = 'Inference time: %.2f ms' % (t * 1000.0 / cv2.getTickFrequency())

        if img is not None:
            print("IMG IS NOT NONE")
            cv2.putText(img, label, (20, 40), FONT_FACE, FONT_SCALE,  (0, 0, 255), THICKNESS, cv2.LINE_AA)
            # cv2.imshow('Output', img)
            image_message = bridge.cv2_to_imgmsg(img, encoding="bgr8")
            topic.publish(image_message)
            
            cv2.waitKey(300)
