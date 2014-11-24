__author__ = 'Chris'
import picamera
import math
import datetime
import cv2
import io
import numpy as np
import httplib
import time

stream = io.BytesIO()

CAMERA_WIDTH = 2592
CAMERA_HEIGHT = 1944

# Take a picture using picamera
with picamera.PiCamera() as camera:
    camera.resolution = (CAMERA_WIDTH, CAMERA_HEIGHT)
    camera.awb_mode = 'shade'
    camera.start_preview()
    time.sleep(5)
    camera.capture(stream, format='jpeg')

data = np.fromstring(stream.getvalue(), dtype=np.uint8)

#import the picture into openCV
image = cv2.imdecode(data, 1)

# write original image if needed for off-line processing
#cv2.imwrite("oilorig.jpg",image)

# uncomment for off-line processing to use saved image
#image = cv2.imread("oilorig.jpg")

# due to physical mounting requirements of camera, rotate image for meter readable orientation
image = cv2.transpose(image)
image = cv2.flip(image, 0)

# making a copy of the image for processing, process in grayscale
img = image
imggray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)

imggray = cv2.blur(imggray,(5,5))
ret,imgbinary = cv2.threshold(imggray, 50, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
ret,imgbinary = cv2.threshold(imggray, ret + 30, 255, cv2.THRESH_BINARY)

# write out or show processed image for debugging
#cv2.imwrite("bin.jpg",imgbinary)
#cv2.imshow("thresh", imgbinary)

#find largest blob, the white background of the meter
# switch for pc/pi, depending if running on pi library or PC return value may require 2 or 3 vars
# imgcont, contours,hierarchy = cv2.findContours(imgbinary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
contours,hierarchy = cv2.findContours(imgbinary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
maxarea = 0
index = 0
meterContour = 0
for c in contours:
    area = cv2.contourArea(c)
    if (area > maxarea):
        maxarea = area
        meterContour = index
    index = index + 1

# find the largest child blob of the white background, should be the needle
maxarea = 0
index = hierarchy[0, meterContour, 2]
needleContour = 0
while (index >= 0):
    c = contours[index]
    area = cv2.contourArea(c)
    if (area > maxarea):
        maxarea = area
        needleContour = index
    index = hierarchy[0,index,0]

# find the largest child blob of the needle contour, should be only one, the pivot point
maxarea = 0
index = hierarchy[0, needleContour, 2]
pivotContour = 0
while (index >= 0):
    c = contours[index]
    area = cv2.contourArea(c)
    if (area > maxarea):
        maxarea = area
        pivotContour = index
    index = hierarchy[0,index,0]

# compute line from contour and point of needle, from this we will get the measurement angle
# the line however lacks direction and may be off +/- 180 degrees, use the pivot centroid to fix
[line_vx,line_vy,line_x,line_y] = cv2.fitLine(contours[needleContour],2,0,0.01,0.01)
needlePt = (line_x,line_y)

# moments of the pivot contour, and the centroid of the pivot contour
pivotMoments = cv2.moments(contours[pivotContour])
pivotPt = (int(pivotMoments['m10'] / pivotMoments['m00']), int(pivotMoments['m01'] / pivotMoments['m00']))

# find the vector from the pivot centroid to the needle line center
dx = needlePt[0] - pivotPt[0]
dy = needlePt[1] - pivotPt[1]

# if dot product of needle-pivot vector and line is negative, flip the line direction
# so the line angle will be oriented correctly
if (line_vx * dx + line_vy * dy < 0):
    line_vx = -line_vx;
    line_vy = -line_vy;

# with the corrected line vector, compute the angle and convert to degrees
line_angle = math.atan2(line_vy, line_vx) * 180 / math.pi
print line_angle

# normalize the angle of the meter
# the needle will go from approx 135 on the low end to 35 degrees on the high end
normangle = line_angle
# adjust the ranage so it doesn't wrap around, 135 to 395
if (normangle < 90): normangle = normangle + 360
# set the low end to 0,  0 to 260
normangle = normangle - 135
# normalize to percentage
pct = normangle / 260.0
print pct

# for display / archive purposes crop the image to the meter view using bounding box
minRect = cv2.minAreaRect(contours[meterContour])
box = cv2.cv.BoxPoints(minRect)
box = np.int0(box)

# draw the graphics of the box and needle
cv2.drawContours(img,[box],0,(0,0,255),4)
cv2.drawContours(img,contours,meterContour,(0,255,0),4)
cv2.drawContours(img,contours,needleContour,(255,0,0),4)
nsize = 120
cv2.line(img,(line_x-line_vx*nsize,line_y-line_vy*nsize),(line_x+line_vx*nsize,line_y+line_vy*nsize),(0,0,255),4)

#find min/max xy for cropping
minx = box[0][0]
miny = box[0][1]
maxx = minx
maxy = miny
for i in (1, 3):
    if (box[i][0] < minx): minx = box[i][0]
    if (box[i][1] < miny): miny = box[i][1]
    if (box[i][0] > maxx): maxx = box[i][0]
    if (box[i][1] > maxy): maxy = box[i][1]

# display the percentage above the bounding box
cv2.putText(img,"{:4.1f}%".format(pct * 100),(minx+150,miny-30),cv2.FONT_HERSHEY_SIMPLEX,3.0,(0,255,255),4)

# scale the extents for some background in the cropping
cropscale = 1.5
len2x = cropscale * (maxx - minx) / 2;
len2y = cropscale * (maxy - miny) / 2 ;
len2x = len2y / 3 * 4
avgx = (minx + maxx) / 2
avgy = (miny + maxy) / 2

# find the top-left, bottom-right crop points
cminx = int(avgx - len2x);
cminy = int(avgy - len2y);
cmaxx = int(avgx + len2x);
cmaxy = int(avgy + len2y);

# crop the image and output
imgcrop = img[cminy:cmaxy, cminx:cmaxx]
cv2.imwrite("oil.jpg", imgcrop)

# display for debugging
#imgscaled = cv2.resize(img, (0, 0), 0, 0.2, 0.2)
#imgcropscaled = cv2.resize(imgcrop, (0, 0), 0, 0.5, 0.5)
#cv2.imshow("output", imgscaled)
#cv2.imshow("outputcrop", imgcropscaled)

# create a timestamp for logging
def timestr(fmt="%Y-%m-%d %H:%M:%S "):
    return datetime.datetime.now().strftime(fmt)

# log the result
with open('angle.log','a') as outf:
    outf.write(timestr())
    outf.write('{:5.1f} deg {:4.1%}\n'.format(line_angle, pct))

# the following code will post the percentage to an openHAB server
# in openHAB the item oilLevel is defined as a Number
msg = '{:4.1f}'.format(pct * 100)

web = httplib.HTTP('192.168.2.20:8080')
web.putrequest('POST', '/rest/items/oilLevel')
web.putheader('Content-type', 'text/plain')
web.putheader('Content-length', '%d' % len(msg))
web.endheaders()
web.send(msg)
statuscode, statusmessage, header = web.getreply()
result = web.getfile().read()

# uncomment if debugging with opencv window views
#cv2.waitKey()
#cv2.destroyAllWindows()
