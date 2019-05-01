from cv2 import cv2 as cv
import numpy as np
from kittiloader import calibread, LabelLoader2D3D
from datasets_imgnet import get_keypoints
def draw_3dbbox_from_keypoints(img, keypoints):
    img = np.copy(img)

    color = [190, 0, 255] # (BGR)
    front_color = [255, 230, 0] # (BGR)
    lines = [[0, 3, 7, 4, 0], [1, 2, 6, 5, 1], [0, 1], [2, 3], [6, 7], [4, 5]] # (0 -> 3 -> 7 -> 4 -> 0, 1 -> 2 -> 6 -> 5 -> 1, etc.)
    colors = [front_color, color, color, color, color, color]

    for n, line in enumerate(lines):
        bg = colors[n]
        cv.polylines(img, np.int32([keypoints[line]]), False, bg, lineType=cv.LINE_AA, thickness=2)

    return img

ext = ".txt"
file_id = '006062'
filepath = "../../../val/11/"
calibpath = "../../data/data_object_calib/training/calib"
img2show = cv.imread("/Users/weizhongjin/usc/ee599/final_project_material/data/KITTI/training/image_2/"+file_id +".png")
ploys = LabelLoader2D3D(file_id,filepath,ext,calibpath,ext)
for ploy in ploys:
    output = get_keypoints(ploy["label_3D"]["center"],ploy["label_3D"]["h"],ploy["label_3D"]["w"],ploy["label_3D"]["l"],ploy["label_3D"]["r_y"],ploy["label_3D"]["P0_mat"])
    img2show = draw_3dbbox_from_keypoints(img2show,output)

cv.imwrite("../../../val/output/"+file_id +"_3dbox.png", img2show)

    

    
