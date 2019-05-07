# --------------------------------------------------------
# Tensorflow Faster R-CNN
# Licensed under The MIT License [see LICENSE for details]
# Written by Jiasen Lu, Jianwei Yang, based on code from Ross Girshick
# --------------------------------------------------------
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import _init_paths
import os
import sys
import numpy as np
import argparse
import pprint
import pdb
import time
import cv2
import torch
import torch.utils.data
import pickle
import torch.nn.functional as F
from torch.autograd import Variable
import torch.nn as nn
import torch.optim as optim
from datasets_imgnet import DatasetImgNetAugmentation, DatasetImgNetEval, BoxRegressor # (this needs to be imported before torch, because cv2 needs to be imported before torch for some reason)
from datasets_imgnet import wrapToPi
from transnet import TransNet
import torchvision.transforms as transforms
import torchvision.datasets as dset
from scipy.misc import imread
from roi_data_layer.roidb import combined_roidb
from roi_data_layer.roibatchLoader import roibatchLoader
from model.utils.config import cfg, cfg_from_file, cfg_from_list, get_output_dir
from model.rpn.bbox_transform import clip_boxes
# from model.nms.nms_wrapper import nms
from model.roi_layers import nms
from model.rpn.bbox_transform import bbox_transform_inv
from model.utils.net_utils import save_net, load_net, vis_detections
from model.utils.blob import im_list_to_blob
from model.faster_rcnn.vgg16 import vgg16
from model.faster_rcnn.resnet import resnet
import pdb

try:
    xrange          # Python 2
except NameError:
    xrange = range  # Python 3



lr = cfg.TRAIN.LEARNING_RATE
momentum = cfg.TRAIN.MOMENTUM
weight_decay = cfg.TRAIN.WEIGHT_DECAY
def draw_3dbbox_from_keypoints(img, keypoints):
    img = np.copy(img)

    color = [190, 0, 255] # (BGR)
    front_color = [255, 230, 0] # (BGR)
    lines = [[0, 3, 7, 4, 0], [1, 2, 6, 5, 1], [0, 1], [2, 3], [6, 7], [4, 5]] # (0 -> 3 -> 7 -> 4 -> 0, 1 -> 2 -> 6 -> 5 -> 1, etc.)
    colors = [front_color, color, color, color, color, color]

    for n, line in enumerate(lines):
        bg = colors[n]

        cv2.polylines(img, np.int32([keypoints[line]]), False, bg, lineType=cv2.LINE_AA, thickness=2)

    return img
batch_size = 8
def _get_image_blob(im):
  """Converts an image into a network input.
  Arguments:
    im (ndarray): a color image in BGR order
  Returns:
    blob (ndarray): a data blob holding an image pyramid
    im_scale_factors (list): list of image scales (relative to im) used
      in the image pyramid
  """
  im_orig = im.astype(np.float32, copy=True)
  im_orig -= cfg.PIXEL_MEANS

  im_shape = im_orig.shape
  im_size_min = np.min(im_shape[0:2])
  im_size_max = np.max(im_shape[0:2])

  processed_ims = []
  im_scale_factors = []

  for target_size in cfg.TEST.SCALES:
    im_scale = float(target_size) / float(im_size_min)
    # Prevent the biggest axis from being more than MAX_SIZE
    if np.round(im_scale * im_size_max) > cfg.TEST.MAX_SIZE:
      im_scale = float(cfg.TEST.MAX_SIZE) / float(im_size_max)
    im = cv2.resize(im_orig, None, None, fx=im_scale, fy=im_scale,
            interpolation=cv2.INTER_LINEAR)
    im_scale_factors.append(im_scale)
    processed_ims.append(im)

  # Create a blob to hold the input images
  blob = im_list_to_blob(processed_ims)

  return blob, np.array(im_scale_factors)





cfg.USE_GPU_NMS = True

print('Using config:')
pprint.pprint(cfg)
np.random.seed(cfg.RNG_SEED)

# train set
# -- Note: Use validation set and disable the flipped to enable faster loading.

input_dir = 'vgg16/pascal_voc'
if not os.path.exists(input_dir):
    raise Exception('There is no input directory for loading network from ' + input_dir)
load_name = os.path.join(input_dir,
'faster_rcnn_1_11_560.pth')

pascal_classes = np.asarray(['__background__',
                    'person','car','van','truck','misc','dontcare','cyclist','tram','person_sitting'])

# initilize the network here.

fasterRCNN = vgg16(pascal_classes, pretrained=False, class_agnostic=False)


fasterRCNN.create_architecture()
cuda = True
class_agnostic = False
print("load checkpoint %s" % (load_name))
if cuda > 0:
    checkpoint = torch.load(load_name)
else:
    checkpoint = torch.load(load_name, map_location=(lambda storage, loc: storage))
fasterRCNN.load_state_dict(checkpoint['model'])
if 'pooling_mode' in checkpoint.keys():
    cfg.POOLING_MODE = checkpoint['pooling_mode']
network = TransNet()
network.load_state_dict(torch.load("transfermodel/model_10_2_epoch_400.pth"))
network = network.cuda()

print('load model successfully!')

# pdb.set_trace()

print("load checkpoint %s" % (load_name))

# initilize the tensor holder here.
im_data = torch.FloatTensor(1)
im_info = torch.FloatTensor(1)
num_boxes = torch.LongTensor(1)
gt_boxes = torch.FloatTensor(1)

# ship to cuda
if cuda > 0:
    im_data = im_data.cuda()
    im_info = im_info.cuda()
    num_boxes = num_boxes.cuda()
    gt_boxes = gt_boxes.cuda()

# make variable
im_data = Variable(im_data, volatile=True)
im_info = Variable(im_info, volatile=True)
num_boxes = Variable(num_boxes, volatile=True)
gt_boxes = Variable(gt_boxes, volatile=True)

if cuda > 0:
    cfg.CUDA = True

if cuda > 0:
    fasterRCNN.cuda()

    fasterRCNN.eval()

start = time.time()
max_per_image = 100
thresh = 0.05
vis = True
image_dir = 'images/'
img = cv2.imread(image_dir + '0000000000.png')
imgInfo = img.shape
size = (imgInfo[1], imgInfo[0])

fourcc = cv2.VideoWriter_fourcc('M','J','P','G') #opencv3.0
videoWrite = cv2.VideoWriter( '2.avi', fourcc, 10, size )
# 写入对象 1 file name 2 编码器 3 帧率 4 尺寸大小

webcam_num = -1
# Set up webcam or get image directories
if webcam_num >= 0 :
    cap = cv2.VideoCapture(webcam_num)
    num_images = 0
else:
    imglist = os.listdir(image_dir)
    imglist.sort(reverse = Ture)
    num_images = len(imglist)

print('Loaded Photo: {} images.'.format(num_images))


while (num_images >= 0):
  total_tic = time.time()
  if webcam_num == -1:
    num_images -= 1

  # Get image from the webcam
  if webcam_num >= 0:
    if not cap.isOpened():
      raise RuntimeError("Webcam could not open. Please check connection.")
    ret, frame = cap.read()
    im_in = np.array(frame)
  # Load the demo image
  else:
    im_file = os.path.join(image_dir, imglist[num_images])
    # im = cv2.imread(im_file)
    im_in = np.array(imread(im_file))
  if len(im_in.shape) == 2:
    im_in = im_in[:,:,np.newaxis]
    im_in = np.concatenate((im_in,im_in,im_in), axis=2)
  # rgb -> bgr
  im = im_in[:,:,::-1]

  blobs, im_scales = _get_image_blob(im)
  assert len(im_scales) == 1, "Only single-image batch implemented"
  im_blob = blobs
  im_info_np = np.array([[im_blob.shape[1], im_blob.shape[2], im_scales[0]]], dtype=np.float32)

  im_data_pt = torch.from_numpy(im_blob)
  im_data_pt = im_data_pt.permute(0, 3, 1, 2)
  im_info_pt = torch.from_numpy(im_info_np)

  im_data.data.resize_(im_data_pt.size()).copy_(im_data_pt)
  im_info.data.resize_(im_info_pt.size()).copy_(im_info_pt)
  gt_boxes.data.resize_(1, 1, 5).zero_()
  num_boxes.data.resize_(1).zero_()

  # pdb.set_trace()
  det_tic = time.time()

  rois, cls_prob, bbox_pred, \
  rpn_loss_cls, rpn_loss_box, \
  RCNN_loss_cls, RCNN_loss_bbox, \
  rois_label = fasterRCNN(im_data, im_info, gt_boxes, num_boxes)

  scores = cls_prob.data
  boxes = rois.data[:, :, 1:5]
  class_agnostic = False
  if cfg.TEST.BBOX_REG:
      # Apply bounding-box regression deltas
      box_deltas = bbox_pred.data
      if cfg.TRAIN.BBOX_NORMALIZE_TARGETS_PRECOMPUTED:
      # Optionally normalize targets by a precomputed mean and stdev
        if class_agnostic:
            if cuda > 0:
                box_deltas = box_deltas.view(-1, 4) * torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_STDS).cuda() \
                           + torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_MEANS).cuda()
            else:
                box_deltas = box_deltas.view(-1, 4) * torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_STDS) \
                           + torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_MEANS)

            box_deltas = box_deltas.view(1, -1, 4)
        else:
            if cuda > 0:
                box_deltas = box_deltas.view(-1, 4) * torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_STDS).cuda() \
                           + torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_MEANS).cuda()
            else:
                box_deltas = box_deltas.view(-1, 4) * torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_STDS) \
                           + torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_MEANS)
            box_deltas = box_deltas.view(1, -1, 4 * len(pascal_classes))

      pred_boxes = bbox_transform_inv(boxes, box_deltas, 1)
      pred_boxes = clip_boxes(pred_boxes, im_info.data, 1)
  else:
      # Simply repeat the boxes, once for each class
      pred_boxes = np.tile(boxes, (1, scores.shape[1]))

  pred_boxes /= im_scales[0]

  scores = scores.squeeze()
  pred_boxes = pred_boxes.squeeze()
  det_toc = time.time()
  detect_time = det_toc - det_tic
  misc_tic = time.time()
  if vis:
      im2show = np.copy(im)
  for j in xrange(1, len(pascal_classes)):
      inds = torch.nonzero(scores[:,j]>thresh).view(-1)
      # if there is det
      if inds.numel() > 0:
        cls_scores = scores[:,j][inds]
        _, order = torch.sort(cls_scores, 0, True)
        if class_agnostic:
          cls_boxes = pred_boxes[inds, :]
        else:
          cls_boxes = pred_boxes[inds][:, j * 4:(j + 1) * 4]

        cls_dets = torch.cat((cls_boxes, cls_scores.unsqueeze(1)), 1)
        # cls_dets = torch.cat((cls_boxes, cls_scores), 1)
        cls_dets = cls_dets[order]
        # keep = nms(cls_dets, cfg.TEST.NMS, force_cpu=not cfg.USE_GPU_NMS)
        keep = nms(cls_boxes[order, :], cls_scores[order], cfg.TEST.NMS)
        cls_dets = cls_dets[keep.view(-1).long()]
        #print('dets: {}'.format(cls_dets))
        #print('box: {}'.format(cls_dets[:,0:4]))
        #print('score: {}'.format(cls_dets[:,4]))
        print('--------------')
        k = 0
        if vis:
          dets = cls_dets.cpu().numpy()
          for i in range(np.minimum(10, dets.shape[0])):
              bbox = tuple(int(np.round(x)) for x in dets[i, :4])
              score = dets[i, -1]
              if score > 0.7:
                  u_min = bbox[0] # (left)
                  u_max = bbox[2] # (rigth)
                  v_min = bbox[1] # (top)
                  v_max = bbox[3] # (bottom)
                  print('u:{}-{}'.format(u_min,u_max))
                  print('v:{}-{}'.format(v_min,v_max))
                  w = u_max - u_min
                  h = v_max - v_min
                  u_center = u_min + w/2.0
                  v_center = v_min + h/2.0

        # translate the center by random distances sampled from
        # uniform[-0.1w, 0.1w] and uniform[-0.1h, 0.1h] in u,v directions:
              #u_center = u_center + np.random.uniform(low=-0.1*w, high=0.1*w)
              #v_center = v_center + np.random.uniform(low=-0.1*h, high=0.1*h)

        # randomly scale w and h by factor sampled from uniform[0.9, 1.1]:
              #w = w*np.random.uniform(low=0.9, high=1.1)
              #h = h*np.random.uniform(low=0.9, high=1.1)

              #u_min = u_center - w/2.0
              #u_max = u_center + w/2.0
              #v_min = v_center - h/2.0
             # v_max = v_center + h/2.0

        ########################################################################
        # get the input 2dbbox img crop and resize to 224 x 224:
        ########################################################################
              #bbox_2d_img = im2show[int(np.max([0, v_min])):int(v_max), int(np.max([0, u_min])):int(u_max)]
                  bbox_2d_img = im2show[v_min:v_max, u_min:u_max]
                  print('--------')
                  
                  bbox_2d_img = cv2.resize(bbox_2d_img, (224, 224),interpolation = cv2.INTER_CUBIC)
                  bbox_2d_img = bbox_2d_img.transpose(2,0,1)
                  bbox_2d_img = bbox_2d_img[np.newaxis, :]
                  bbox_2d_img = torch.from_numpy(bbox_2d_img)  
                  bbox_2d_img =  bbox_2d_img.float()
                  bbox_2d_img = bbox_2d_img.cuda()
                  outputs = network(bbox_2d_img)
                  outputs_keypoints = outputs[:, 0:16] # (shape: (batch_size, 2*8))
                  outputs_size = outputs[:, 16:19] # (shape: (batch_size, 3)
                  outputs_distance = outputs[:, 19] # (shape: (batch_size, )
                  outputs_keypoints = outputs_keypoints.data.cpu().numpy()
                  label_keypoints = np.resize(outputs_keypoints, (8, 2))
                  label_keypoints = label_keypoints*np.array([w, h]) + np.array([u_center, v_center])
                  if abs(outputs_distance) < 0.675:
                        cv2.putText(im2show, 'warning', (10,20),cv2.FONT_HERSHEY_PLAIN,
                        2.0, (0, 0, 255), thickness=2)
                  im2show = draw_3dbbox_from_keypoints(im2show,label_keypoints)
          #im2show = vis_detections(im2show, pascal_classes[j], cls_dets.cpu().numpy(), 0.5)
          

  misc_toc = time.time()
  nms_time = misc_toc - misc_tic

  if webcam_num == -1:
      sys.stdout.write('im_detect: {:d}/{:d} {:.3f}s {:.3f}s   \r' \
                       .format(num_images + 1, len(imglist), detect_time, nms_time))
      sys.stdout.flush()

  if vis and webcam_num == -1:
      # cv2.imshow('test', im2show)
      # cv2.waitKey(0)
      # result_path = os.path.join(image_dir, imglist[num_images][:-4] + "_det.png")
      # cv2.imwrite(result_path, im2show)
      videoWrite.write(im2show)
  else:
      im2showRGB = cv2.cvtColor(im2show, cv2.COLOR_BGR2RGB)
      cv2.imshow("frame", im2showRGB)
      total_toc = time.time()
      total_time = total_toc - total_tic
      frame_rate = 1 / total_time
      print('Frame rate:', frame_rate)
      if cv2.waitKey(1) & 0xFF == ord('q'):
          break
if webcam_num >= 0:
  cap.release()
  cv2.destroyAllWindows()

else:
  videoWrite.release()
