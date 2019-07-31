from itertools import count

import torch
import torch.nn as nn
import torch.optim as optim

import random
random.seed(0)
torch.manual_seed(0)

import numpy as np

import sys
import time

from model import Autoencoder

from loss import voxel_difference, kld_loss

from collections import deque

from dataset import dataset as dataset
from util import create_text_slice

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


BATCH_SIZE = 32
TEST_SPLIT = 0.05

all_indices = list(range(dataset.size))
random.shuffle(all_indices)
test_indices = all_indices[:int(dataset.size * TEST_SPLIT)]
training_indices = list(all_indices[int(dataset.size * TEST_SPLIT):])
test_data = dataset.voxels[test_indices]

VIEWER_UPDATE_STEP = 20

autoencoder = Autoencoder()
if "continue" in sys.argv:
    autoencoder.load()

optimizer = optim.Adam(autoencoder.parameters(), lr=0.00005)

show_viewer = "nogui" not in sys.argv

if show_viewer:
    from voxel.viewer import VoxelViewer
    viewer = VoxelViewer()

error_history = deque(maxlen = BATCH_SIZE)

criterion = nn.functional.mse_loss

log_file = open("plots/autoencoder_training.csv", "a" if "continue" in sys.argv else "w")

def create_batches():
    batch_count = int(len(training_indices) / BATCH_SIZE)
    random.shuffle(training_indices)
    for i in range(batch_count - 1):
        yield training_indices[i * BATCH_SIZE:(i+1)*BATCH_SIZE]
    yield training_indices[(batch_count - 1) * BATCH_SIZE:]

def get_reconstruction_loss(input, target):
    difference = input - target
    wrong_signs = target < 0
    difference[wrong_signs] *= 32

    return torch.mean(torch.abs(difference))

def test(epoch_index, epoch_time):
    with torch.no_grad():
        autoencoder.eval()
        output, mean, log_variance = autoencoder.forward(test_data, device)
        
        reconstruction_loss = get_reconstruction_loss(output, test_data)
        kld = kld_loss(mean, log_variance)

        voxel_diff = voxel_difference(output, test_data)
        inception_score = autoencoder.get_inception_score(device = device)

        if "show_slice" in sys.argv:
            print(create_text_slice(output[0, :, :, :]))

        print("Epoch {:d} ({:.1f}s): ".format(epoch_index, epoch_time) +
            "Reconstruction loss: {:.4f}, ".format(reconstruction_loss) +
            "Voxel diff: {:.4f}, ".format(voxel_diff) + 
            "KLD loss: {:4f}, ".format(kld) + 
            "training loss: {:4f}, ".format(sum(error_history) / len(error_history)) +
            "inception score: {:4f}".format(inception_score)
        )

        log_file.write('{:d} {:.1f} {:.6f} {:.6f} {:.6f} {:.6f}\n'.format(epoch_index, epoch_time, reconstruction_loss, kld, voxel_diff, inception_score))
        log_file.flush()

def train():    
    for epoch in count():
        batch_index = 0
        epoch_start_time = time.time()
        for batch in create_batches():
            try:
                indices = torch.tensor(batch, device = device)
                sample = dataset.voxels[indices, :, :, :]

                autoencoder.zero_grad()
                autoencoder.train()
                output, mean, log_variance = autoencoder.forward(sample, device)
                reconstruction_loss = get_reconstruction_loss(output, sample)
                error_history.append(reconstruction_loss.item())
                kld = kld_loss(mean, log_variance)

                loss = reconstruction_loss + kld
                
                loss.backward()
                optimizer.step()        

                error = loss.item()

                if show_viewer and batch_index == 0:
                    viewer.set_voxels(output[0, :, :, :].squeeze().detach().cpu().numpy())

                if show_viewer and (batch_index + 1) % VIEWER_UPDATE_STEP == 0 and 'verbose' in sys.argv:
                    viewer.set_voxels(output[0, :, :, :].squeeze().detach().cpu().numpy())
                    print("epoch " + str(epoch) + ", batch " + str(batch_index) \
                        + ', reconstruction loss: {0:.4f}'.format(reconstruction_loss.item()) \
                        + ' (average: {0:.4f}), '.format(sum(error_history) / len(error_history)) \
                        + 'KLD loss: {0:.4f}'.format(kld))
                batch_index += 1
            except KeyboardInterrupt:
                if show_viewer:
                    viewer.stop()
                return
        autoencoder.save()
        test(epoch, time.time() - epoch_start_time)

train()
exit()
