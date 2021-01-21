# Copyright (c) 2020, Soohwan Kim. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
import pdb

class LabelSmoothedCrossEntropyLoss(nn.Module):
    """
    Label smoothed cross entropy loss function.

    Args:
        num_classes (int): the number of classfication
        ignore_index (int): Indexes that are ignored when calculating loss
        smoothing (float): ratio of smoothing (confidence = 1.0 - smoothing)
        dim (int): dimension of calculation loss
        reduction (str): reduction method [sum, mean] (default: sum)
        architecture (str): speech model`s model [las, transformer] (default: las)

    Inputs: logit, target
        logit (torch.Tensor): probability distribution value from model and it has a logarithm shape
        target (torch.Tensor): ground-thruth encoded to integers which directly point a word in label

    Returns: label_smoothed
        - **label_smoothed** (float): sum of loss
    """
    def __init__(
            self,
            num_classes: int,           # the number of classfication
            ignore_index: int,          # indexes that are ignored when calcuating loss
            smoothing: float = 0.1,     # ratio of smoothing (confidence = 1.0 - smoothing)
            dim: int = -1,              # dimension of caculation loss
            reduction='sum',            # reduction method [sum, mean]
            architecture='las'          # speech model`s model [las, transformer]
    ) -> None:
        super(LabelSmoothedCrossEntropyLoss, self).__init__()
        self.confidence = 1.0 - smoothing
        self.smoothing = smoothing
        self.num_classes = num_classes
        self.dim = dim
        self.ignore_index = ignore_index
        self.reduction = reduction.lower()
        self.architecture = architecture.lower()

        if self.reduction == 'sum':
            self.reduction_method = torch.sum
        elif self.reduction == 'mean':
            self.reduction_method = torch.mean
        else:
            raise ValueError("Unsupported reduction method {0}".format(reduction))

    def forward(self, logit: Tensor, target: Tensor):
        if self.architecture == 'transformer':
            logit = F.log_softmax(logit, dim=-1)

        if self.smoothing > 0.0:
            with torch.no_grad():
                label_smoothed = torch.zeros_like(logit)
                label_smoothed.fill_(self.smoothing / (self.num_classes - 1))
                label_smoothed.scatter_(1, target.data.unsqueeze(1), self.confidence)
                label_smoothed[target == self.ignore_index, :] = 0
            return self.reduction_method(-label_smoothed * logit)

        return F.cross_entropy(logit, target, ignore_index=self.ignore_index, reduction=self.reduction)
