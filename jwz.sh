cd lib
mkdir data
pip install -r requirements.txt
python setup.py build develop
cd ../data
git clone https://github.com/pdollar/coco.git
cd coco/PythonAPI
make
cd ../../..
mkdir VOCdevkit2007
cd VOCdevkit2007
wget https://s3.amazonaws.com/weizhongjin/VOC2012.zip
unzip VOC2012.zip
mv VOC2012 VOC2007
cd VOC2007/ImageSets/Main
rm trainval.txt
wget https://s3.amazonaws.com/weizhongjin/txt.zip
unzip txt.zip
cd ../../../../..
CUDA_VISIBLE_DEVICES=0 python trainval_net.py --dataset pascal_voc --net vgg16 --bs 12 --nw 1  --cuda
