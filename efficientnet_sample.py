from __future__ import print_function, division

import torch
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
from torchvision import datasets, models, transforms
import time
import os
from efficientnet.model import EfficientNet

import argparse

# some parameters
use_gpu = torch.cuda.is_available()
print(use_gpu)

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

data_dir = ''
num_epochs = 40
batch_size = 2
input_size = 4
class_num = 3
weights_loc = ""
lr = 0.01
net_name = 'efficientnet-b3'
epoch_to_resume_from = 0
momentum = 0.9
project_name = ""
test_batch_size = 4
test_only = False

train_dir = ""
val_dir = ""


def loaddata(data_dir, batch_size, set_name, shuffle):
    data_transforms = {
        'train': transforms.Compose([
            transforms.Resize(input_size),
            transforms.CenterCrop(input_size),
    #        transforms.RandomAffine(degrees=0, translate=(0.05, 0.05)),
    #        transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
        'test': transforms.Compose([
            transforms.Resize(input_size),
            transforms.CenterCrop(input_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
    }

    image_datasets = {x: datasets.ImageFolder(os.path.join(data_dir, x), data_transforms[x]) for x in [set_name]}
    # num_workers=0 if CPU else =1
    dataset_loaders = {x: torch.utils.data.DataLoader(image_datasets[x],
                                                      batch_size=batch_size,
                                                      shuffle=shuffle, num_workers=1, drop_last = True) for x in [set_name]}
    data_set_sizes = len(image_datasets[set_name])
    return dataset_loaders, data_set_sizes


def train_model(model_ft, criterion, optimizer, lr_scheduler, num_epochs=50):
    
    train_loss = []
    since = time.time()
    best_model_wts = model_ft.state_dict()
    best_acc = 0.0
    best_acc_epoch = 0
    model_ft.train(True)
    save = 0


    for epoch in range(epoch_to_resume_from, num_epochs):

        dset_loaders, dset_sizes = loaddata(data_dir=data_dir, batch_size=batch_size, set_name='train', shuffle=True)
        print('Data Size', dset_sizes)
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-' * 10)
        optimizer = lr_scheduler(optimizer, epoch)

        running_loss = 0.0
        running_corrects = 0
        count = 0

        for data in dset_loaders['train']:
            inputs, labels = data
            labels = torch.squeeze(labels.type(torch.LongTensor))
            if use_gpu:
                inputs, labels = Variable(inputs.cuda()), Variable(labels.cuda())
            else:
                inputs, labels = Variable(inputs), Variable(labels)

            outputs = model_ft(inputs)
            
            if count % 1200 == 0:
                print(outputs)
                print(labels)
            
            loss = criterion(outputs, labels)
            _, preds = torch.max(outputs.data, 1)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            count += 1
            if count % 120 == 0 or outputs.size()[0] < batch_size:
                print('Epoch:{}: loss:{:.3f}'.format(epoch, loss.item()))
                train_loss.append(loss.item())

            running_loss += loss.item() * inputs.size(0)
            running_corrects += torch.sum(preds == labels.data)

        train_loss = running_loss / dset_sizes
        train_acc = running_corrects.double() / dset_sizes

        print("\nTrain epoch finished.")

        print('Loss: {:.4f} Acc: {:.4f}'.format(
            train_loss, train_acc))
        
        write_to_file(train_dir, str(train_loss) + " " + str(train_acc))

        running_loss = 0.0
        running_corrects = 0
        cont = 0
        outPre = []
        outLabel = []

        dset_loaders, dset_sizes = loaddata(data_dir=data_dir, batch_size=test_batch_size, set_name='test', shuffle=False)

        print("\nVal starting...")

        for data in dset_loaders['test']:
            inputs, labels = data
            labels = torch.squeeze(labels.type(torch.LongTensor))
            inputs, labels = Variable(inputs.cuda()), Variable(labels.cuda())
            outputs = model_ft(inputs)
            _, preds = torch.max(outputs.data, 1)
            loss = criterion(outputs, labels)
            if cont == 0:
                outPre = outputs.data.cpu()
                outLabel = labels.data.cpu()
            else:
                outPre = torch.cat((outPre, outputs.data.cpu()), 0)
                outLabel = torch.cat((outLabel, labels.data.cpu()), 0)
            running_loss += loss.item() * inputs.size(0)
            running_corrects += torch.sum(preds == labels.data)
            cont += 1

        val_loss = running_loss / dset_sizes
        val_acc = running_corrects.double() / dset_sizes

        print('Val Loss: {:.4f} Val Acc: {:.4f}'.format(val_loss, val_acc))

        write_to_file(val_dir, str(val_loss) + " " + str(val_acc))

        print("Val finished.\n")


        if val_acc > best_acc:
            
            print("new best model!... with former accuracy of {:.4f} at epoch: {:.4f}, surpassed by {:.4f} at epoch: {:.4f}!.\n".format(best_acc, epoch, val_acc, best_acc_epoch))
            best_acc_epoch = epoch
            best_acc = val_acc
            best_model_wts = model_ft.state_dict()

        save += 1
        
        if save % 5 == 4:
            print("saving best model regularly...\n")
            save_dir = data_dir + '/model/'
            model_ft.load_state_dict(best_model_wts)
            model_out_path = save_dir + project_name + "_" + net_name + "_"+ str(best_acc_epoch) + str(best_acc) + '.pth'
            torch.save(model_ft, model_out_path)
        
        if train_acc > 0.999:
            break

    # save best model
    save_dir = data_dir + '/model'
    model_ft.load_state_dict(best_model_wts)
    model_out_path = save_dir + project_name + "_" + net_name + "_"+ str(best_acc_epoch) + str(best_acc) + '.pth'
    torch.save(model_ft, model_out_path)

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))

    return train_loss, best_model_wts


def test_model(model, criterion):
    model.eval()
    running_loss = 0.0
    running_corrects = 0
    cont = 0
    outPre = []
    outLabel = []
    dset_loaders, dset_sizes = loaddata(data_dir=data_dir, batch_size=test_batch_size, set_name='test', shuffle=False)
    for data in dset_loaders['test']:
        inputs, labels = data
        labels = torch.squeeze(labels.type(torch.LongTensor))
        inputs, labels = Variable(inputs.cuda()), Variable(labels.cuda())
        outputs = model(inputs)
        _, preds = torch.max(outputs.data, 1)
        loss = criterion(outputs, labels)
        if cont == 0:
            outPre = outputs.data.cpu()
            outLabel = labels.data.cpu()
        else:
            outPre = torch.cat((outPre, outputs.data.cpu()), 0)
            outLabel = torch.cat((outLabel, labels.data.cpu()), 0)
        running_loss += loss.item() * inputs.size(0)
        running_corrects += torch.sum(preds == labels.data)
        cont += 1
    print('Test Loss: {:.4f} Test Acc: {:.4f}'.format(running_loss / dset_sizes,
                                            running_corrects.double() / dset_sizes))


def exp_lr_scheduler(optimizer, epoch, init_lr=0.01, lr_decay_epoch=10):
    """Decay learning rate by a f#            model_out_path ="./model/W_epoch_{}.pth".format(epoch)
#            torch.save(model_W, model_out_path) actor of 0.1 every lr_decay_epoch epochs."""
    lr = init_lr * (0.8**(epoch // lr_decay_epoch))
    print('LR is set to {}'.format(lr))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr

    return optimizer


def write_to_file(path, num):
    print(f"writing to file: {path}... "  )
    f = open(path, ""a+)
    f.write(num + "\n")
    f.close()
    print("write successful!...\n")

def run():
    # train
    pth_map = {
        'efficientnet-b0': 'efficientnet-b0-355c32eb.pth',
        'efficientnet-b1': 'efficientnet-b1-f1951068.pth',
        'efficientnet-b2': 'efficientnet-b2-8bb594d6.pth',
        'efficientnet-b3': 'efficientnet-b3-5fb5a3c3.pth',
        'efficientnet-b4': 'efficientnet-b4-6ed6700e.pth',
        'efficientnet-b5': 'efficientnet-b5-b6417697.pth',
        'efficientnet-b6': 'efficientnet-b6-c76e70fd.pth',
        'efficientnet-b7': 'efficientnet-b7-dcc49843.pth',
    }



    if weights_loc != None:
        model_ft = torch.load(weights_loc)
    else:
            # Modify the fully connected layer, if model not going to be loaded
        model_ft = EfficientNet.from_pretrained(net_name)
        num_ftrs = model_ft._fc.in_features
        model_ft._fc = nn.Linear(num_ftrs, class_num)    

    criterion = nn.CrossEntropyLoss()

    if use_gpu:
        model_ft = model_ft.cuda()
        criterion = criterion.cuda()

    optimizer = optim.SGD((model_ft.parameters()), lr=lr,
                        momentum=momentum, weight_decay=0.0004)

    if not test_only:
        train_loss, best_model_wts = train_model(model_ft, criterion, optimizer, exp_lr_scheduler, num_epochs=num_epochs)
        model_ft.load_state_dict(best_model_wts)


    # test
    print('-' * 10)
    print('Test Accuracy:')

    criterion = nn.CrossEntropyLoss().cuda()

    test_model(model_ft, criterion)



if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    parser.add_argument('--data-dir', type=str, default=None, help='path of /dataset/')
    parser.add_argument('--num-epochs', type=int, default=40)
    parser.add_argument('--batch-size', type=int, default=4, help='total batch size for all GPUs')
    parser.add_argument('--img-size', type=int, default=[1024, 1024], help='img sizes')
    parser.add_argument('--class-num', type=int, default=3, help='class num')

    parser.add_argument('--weights-loc', type=str, default= None, help='path of weights (if going to be loaded)')

    parser.add_argument("--lr", type=float, default= 0.01, help="learning rate")
    parser.add_argument("--net-name", type=str, default="efficientnet-b3", help="efficientnet type")

    parser.add_argument('--resume-epoch', type=int, default=0, help='what epoch to start from')

    parser.add_argument('--momentum', type=float, default=0.9, help='momentum')
    
    parser.add_argument("--project-name", type=str, default="", help= "name to save weights")

    parser.add_argument("--test-batch-size", type=int, default=4, help="batch size for test")

    parser.add_argument("--test-only", type=bool, default=False, help="set True if you only want test")

    opt = parser.parse_args()

    data_dir = opt.data_dir
    num_epochs = opt.num_epochs
    batch_size = opt.batch_size
    input_size = opt.img_size
    class_num = opt.class_num

    weights_loc = opt.weights_loc

    lr = opt.lr
    net_name = opt.net_name

    epoch_to_resume_from = opt.resume_epoch

    momentum = opt.momentum

    project_name = opt.project_name

    test_batch_size = opt.test_batch_size

    test_only = opt.test_only
    
    print("data dir: ", data_dir, ",  num epochs: ", num_epochs, ",  batch size: ",batch_size,
             ", img size: ", input_size, ", num of classes:", class_num, ", .pth weights file location:", weights_loc,
             ", learning rate:", lr, ", net name:", net_name, ", epoch to resume from: ", epoch_to_resume_from,
             ", momentum: ",momentum, ", project name:", project_name,", test batch size:", test_batch_size)
    
    train_dir = data_dir + "/model/train.txt" 
    val_dir = data_dir + "/model/val.txt"

    run()
