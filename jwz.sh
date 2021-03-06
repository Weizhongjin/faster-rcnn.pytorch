mkdir data
pip install -r requirements.txt
cd lib
python setup.py build develop
cd ../data
mkdir imagenet_weights
cd imagenet_weights
python ../../pretrain_model.py
wget https://s3.amazonaws.com/pytorch/models/resnet50-19c8e357.pth
mv resnet50-19c8e357.pth resnet50.pth
cd ..
git clone https://github.com/pdollar/coco.git
cd coco/PythonAPI
make
cd ../..
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
mkdir vgg16
cd vgg16
mkdir pascal_voc
cd ..


