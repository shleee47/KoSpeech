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

import math
import time
import torch
import torch.nn as nn
import pdb
import queue
import pandas as pd
from torch import Tensor
from typing import Tuple
from kospeech.optim import Optimizer
from kospeech.vocabs import Vocabulary
from kospeech.checkpoint import Checkpoint
from kospeech.metrics import CharacterErrorRate
from kospeech.utils import logger
from kospeech.criterion import (
    LabelSmoothedCrossEntropyLoss,
    JointCTCCrossEntropyLoss,
)
from kospeech.data import (
    MultiDataLoader,
    AudioDataLoader,
    SpectrogramDataset,
)
from torch.utils.tensorboard import SummaryWriter

class SupervisedTrainer(object):
    """
    The SupervisedTrainer class helps in setting up training framework in a supervised setting.

    Args:
        optimizer (kospeech.optim.__init__.Optimizer): optimizer for training
        criterion (torch.nn.Module): loss function
        trainset_list (list): list of training datset
        validset (kospeech.data.data_loader.SpectrogramDataset): validation dataset
        num_workers (int): number of using cpu cores
        device (torch.device): device - 'cuda' or 'cpu'
        print_every (int): number of timesteps to print result after
        save_result_every (int): number of timesteps to save result after
        checkpoint_every (int): number of timesteps to checkpoint after
    """
    train_dict = {'loss': [], 'cer': []}
    valid_dict = {'loss': [], 'cer': []}
    train_step_result = {'loss': [], 'cer': []}
    TRAIN_RESULT_PATH = "train_result.csv"
    VALID_RESULT_PATH = "eval_result.csv"
    TRAIN_STEP_RESULT_PATH = "train_step_result.csv"

    def __init__(
            self,
            optimizer: Optimizer,                          # optimizer for training
            criterion: nn.Module,                          # loss function
            trainset_list: list,                           # list of training dataset
            validset: SpectrogramDataset,                  # validation dataset
            num_workers: int,                              # number of threads
            device: torch.device,                          # device - cuda or cpu
            print_every: int,                              # number of timesteps to save result after
            save_result_every: int,                        # nimber of timesteps to save result after
            checkpoint_every: int,                         # number of timesteps to checkpoint after
            teacher_forcing_step: float = 0.2,             # step of teacher forcing ratio decrease per epoch.
            min_teacher_forcing_ratio: float = 0.8,        # minimum value of teacher forcing ratio
            architecture: str = 'las',                     # model to train - las, transformer
            vocab: Vocabulary = None,                      # vocabulary object
            joint_ctc_attention: bool = False,              # flag indication whether joint CTC-Attention or not
    ) -> None:
        self.num_workers = num_workers
        self.optimizer = optimizer
        self.criterion = criterion
        self.trainset_list = trainset_list
        self.validset = validset
        self.print_every = print_every
        self.save_result_every = save_result_every
        self.checkpoint_every = checkpoint_every
        self.device = device
        self.teacher_forcing_step = teacher_forcing_step
        self.min_teacher_forcing_ratio = min_teacher_forcing_ratio
        self.metric = CharacterErrorRate(vocab)
        self.architecture = architecture.lower()
        self.vocab = vocab
        #self.joint_ctc_attention = joint_ctc_attention
        self.joint_ctc_attention = False
        self.writer = SummaryWriter()
        self.writer_idx = 0
        if self.joint_ctc_attention:
            self.log_format = "step: {:4d}/{:4d}, loss: {:.6f}, ctc_loss: {:.6f}, ce_loss: {:.6f}, " \
                              "cer: {:.2f}, elapsed: {:.2f}s {:.2f}m {:.2f}h, lr: {:.6f}"
        else:
            self.log_format = "step: {:4d}/{:4d}, loss: {:.6f}, " \
                              "cer: {:}, elapsed: {:.2f}s {:.2f}m {:.2f}h, lr: {:.6f}"

    def train(
        self,
        model: nn.Module,                           # model to train
        batch_size: int,                            # batch size for experiment
        epoch_time_step: int,                       # number of time step for training
        num_epochs: int,                            # number of epochs (iteration) for training
        teacher_forcing_ratio: float = 0.99,        # teacher forcing ratio
        resume: bool = False,                        # resume training with the latest checkpoint
    ) -> nn.Module:
        """
        Run training for a given model.

        Args:
            model (torch.nn.Module): model to train
            batch_size (int): batch size for experiment
            epoch_time_step (int): number of time step for training
            num_epochs (int): number of epochs for training
            teacher_forcing_ratio (float): teacher forcing ratio (default 0.99)
            resume(bool, optional): resume training with the latest checkpoint, (default False)
        """
        start_epoch = 0
        if resume:
            checkpoint = Checkpoint()
            wanted_checkpoint_path = checkpoint.get_wanted_checkpoint()
            resume_checkpoint = checkpoint.load(wanted_checkpoint_path,wanted=True)
            #latest_checkpoint_path = checkpoint.get_latest_checkpoint()
            #resume_checkpoint = checkpoint.load(latest_checkpoint_path)
            #model = resume_checkpoint.model
            model.load_state_dict(resume_checkpoint.model.state_dict())
            #self.optimizer = resume_checkpoint.optimizer
            #self.trainset_list = resume_checkpoint.trainset_list
            #self.validset = resume_checkpoint.validset
            start_epoch = resume_checkpoint.epoch + 1
            epoch_time_step = 0

            for trainset in self.trainset_list:
                epoch_time_step += len(trainset)

            epoch_time_step = math.ceil(epoch_time_step / batch_size)

        logger.info('start')
        train_begin_time = time.time()

        for epoch in range(start_epoch, num_epochs):
#            logger.info('Epoch %d start' % epoch)
#            train_queue = queue.Queue(self.num_workers << 1)
#
#            for trainset in self.trainset_list:
#                trainset.shuffle()
#
#            # Training
#            train_loader = MultiDataLoader(
#                self.trainset_list, train_queue, batch_size, self.num_workers, self.vocab.pad_id
#            )
#            train_loader.start()
#
#            model, train_loss, train_cer = self.__train_epoches(
#                model=model,
#                epoch=epoch,
#                epoch_time_step=epoch_time_step,
#                train_begin_time=train_begin_time,
#                queue=train_queue,
#                teacher_forcing_ratio=teacher_forcing_ratio,
#            )
#            train_loader.join()
#            Checkpoint(model, self.optimizer, self.trainset_list, self.validset, epoch).save()
#            logger.info('Epoch %d (Training) Loss %0.4f CER %0.4f' % (epoch, train_loss, train_cer))
#
#            teacher_forcing_ratio -= self.teacher_forcing_step
#            teacher_forcing_ratio = max(self.min_teacher_forcing_ratio, teacher_forcing_ratio)
#
            # Validation
            valid_queue = queue.Queue(self.num_workers << 1)
            valid_loader = AudioDataLoader(self.validset, valid_queue, batch_size, 0, self.vocab.pad_id)
            valid_loader.start()

            valid_cer = self.validate(model, valid_queue)
            '''Tensorboard'''
            self.writer.add_scalar('/valid/cer',valid_cer,epoch)
                
            valid_loader.join()

            logger.info('Epoch %d CER %0.4f' % (epoch, valid_cer))
#            self.__save_epoch_result(train_result=[self.train_dict, train_loss, train_cer],
#                                     valid_result=[self.valid_dict, train_loss, valid_cer])
            logger.info('Epoch %d Training result saved as a csv file complete !!' % epoch)
            torch.cuda.empty_cache()

        Checkpoint(model, self.optimizer, self.criterion, self.trainset_list, self.validset, num_epochs).save()
        return model

    def __train_epoches(
            self, model: nn.Module,
            epoch: int,
            epoch_time_step: int,
            train_begin_time: float,
            queue: queue.Queue,
            teacher_forcing_ratio: float,
    ) -> Tuple[nn.Module, float, float]:
        """
        Run training one epoch

        Args:
            model (torch.nn.Module): model to train
            epoch (int): number of current epoch
            epoch_time_step (int): total time step in one epoch
            train_begin_time (float): time of train begin
            queue (queue.Queue): training queue, containing input, targets, input_lengths, target_lengths
            teacher_forcing_ratio (float): teaching forcing ratio (default 0.99)

        Returns: loss, cer
            - **loss** (float): loss of current epoch
            - **cer** (float): character error rate of current epoch
        """
        cer = 1.0
        epoch_loss_total = 0.
        total_num = 0
        timestep = 0

        model.train()

        begin_time = epoch_begin_time = time.time()
        num_workers = self.num_workers

        while True:
            inputs, targets, input_lengths, target_lengths = queue.get()

            if inputs.shape[0] == 0:
                # Empty feats means closing one loader
                num_workers -= 1
                logger.debug('left train_loader: %d' % num_workers)

                if num_workers == 0:
                    break
                else:
                    continue

            self.optimizer.zero_grad()

            inputs = inputs.to(self.device)
            targets = targets.to(self.device)
            input_lengths = input_lengths.to(self.device)
            target_lengths = torch.as_tensor(target_lengths).to(self.device)

            model = model.to(self.device)
            output, loss, ctc_loss, cross_entropy_loss = self.model_forward(
                teacher_forcing_ratio=teacher_forcing_ratio,
                inputs=inputs,
                input_lengths=input_lengths,
                targets=targets,
                target_lengths=target_lengths,
                model=model
            )
            y_hats = output.max(-1)[1]
            print('--------------------------------------')
            print('targets: ',targets)
            print('y_hats: ',y_hats)
            cer = self.metric(targets, y_hats)
            total_num += int(input_lengths.sum())

            loss.backward()
            self.optimizer.step(model)
            epoch_loss_total += loss.item()

            timestep += 1
            torch.cuda.empty_cache()
           
            '''Tensorboard'''
            if timestep % (epoch_time_step//1000) == 0:
                self.writer_idx+=1
                self.writer.add_scalar('/train/cer',cer,self.writer_idx)
                self.writer.add_scalar('/train/loss',loss,self.writer_idx)
                self.writer.add_scalar('/train/lr',self.optimizer.get_lr(),self.writer_idx)
                if self.joint_ctc_attention:
                    self.writer.add_scalar('/train/ctc_loss',ctc_loss,self.writer_idx)
                    self.writer.add_scalar('/train/ce_loss',cross_entropy_loss,self.writer_idx)
            
            if timestep % self.print_every == 0:
                current_time = time.time()
                elapsed = current_time - begin_time
                epoch_elapsed = (current_time - epoch_begin_time) / 60.0
                train_elapsed = (current_time - train_begin_time) / 3600.0

                if self.joint_ctc_attention:
                    logger.info(self.log_format.format(
                        timestep, epoch_time_step,
                        loss,
                        ctc_loss, cross_entropy_loss,
                        cer,
                        elapsed, epoch_elapsed, train_elapsed,
                        self.optimizer.get_lr()
                    ))
                else:
                    logger.info(self.log_format.format(
                        timestep, epoch_time_step,
                        loss,
                        cer,
                        elapsed, epoch_elapsed, train_elapsed,
                        self.optimizer.get_lr()
                    ))
                begin_time = time.time()

            if timestep % self.save_result_every == 0:
                self.__save_step_result(self.train_step_result, epoch_loss_total / total_num, cer)

            if timestep % self.checkpoint_every == 0:
                Checkpoint(model, self.optimizer,  self.trainset_list, self.validset, epoch).save()

            del inputs, input_lengths, targets, output, loss, y_hats

        Checkpoint(model, self.optimizer, self.trainset_list, self.validset, epoch).save()
        logger.info('train() completed')

        return model, epoch_loss_total / total_num, cer

    def validate(self, model: nn.Module, queue: queue.Queue) -> float:
        """
        Run training one epoch

        Args:
            model (torch.nn.Module): model to train
            queue (queue.Queue): validation queue, containing input, targets, input_lengths, target_lengths

        Returns: loss, cer
            - **loss** (float): loss of validation
            - **cer** (float): character error rate of validation
        """
        target_list = list()
        predict_list = list()
        
        cer = 1.0

        model.eval()
        logger.info('validate() start')
        while True:
            inputs, targets, input_lengths, target_lengths = queue.get()

            if inputs.shape[0] == 0:
                break

            inputs = inputs.to(self.device)
            targets = targets[:, 1:].to(self.device)
            model.to(self.device)

            if isinstance(model, nn.DataParallel):
                y_hats = model.module.greedy_search(inputs, input_lengths, self.device)
            else:
                y_hats = model.greedy_search(inputs, input_lengths, self.device)
            
            
            for idx in range(targets.size(0)):
                target_list.append(self.vocab.label_to_string(targets[idx]))
                predict_list.append(self.vocab.label_to_string(y_hats[idx].cpu().detach().numpy()))
             
            cer = self.metric(targets, y_hats)
            print('--------------------------')
            print('targets: ',targets)
            print('y_hat: ',y_hats)
            print('cer :',cer)
        self._save_result(target_list,predict_list)    
        logger.info('validate() completed')

        return cer

    def model_forward(
            self,
            model: nn.Module,
            inputs: Tensor,
            input_lengths: Tensor,
            targets: Tensor,
            target_lengths: Tensor,
            teacher_forcing_ratio: float
    ) -> Tuple[Tensor, Tensor, Tensor, Tensor]:
        ctc_loss = None
        cross_entropy_loss = None
        if self.architecture == 'las':
            if isinstance(model, nn.DataParallel):
                model.module.flatten_parameters()
            else:
                model.flatten_parameters()

            decoder_outputs, encoder_log_probs, encoder_output_lengths = model(
                inputs=inputs,
                input_lengths=input_lengths,
                targets=targets,
                teacher_forcing_ratio=teacher_forcing_ratio
            )

            outputs = torch.stack(decoder_outputs['decoder_log_probs'], dim=1).to(self.device)

            if isinstance(self.criterion, LabelSmoothedCrossEntropyLoss):
                loss = self.criterion(
                    outputs.contiguous().view(-1, outputs.size(-1)), targets[:, 1:].contiguous().view(-1)
                )
            elif isinstance(self.criterion, JointCTCCrossEntropyLoss):
                loss, ctc_loss, cross_entropy_loss = self.criterion(
                    encoder_log_probs=encoder_log_probs.transpose(0, 1),
                    decoder_log_probs=outputs.contiguous().view(-1, outputs.size(-1)),
                    output_lengths=encoder_output_lengths,
                    targets=targets,
                    target_lengths=target_lengths
                )
            else:
                raise ValueError(f"Unsupported Criterion: {self.criterion}")

        elif self.architecture == 'transformer':
            outputs, encoder_log_probs, encoder_output_lengths = model(inputs, input_lengths, targets)
            if isinstance(self.criterion, LabelSmoothedCrossEntropyLoss):
                loss = self.criterion(
                    outputs.contiguous().view(-1, outputs.size(-1)), targets[:, 1:].contiguous().view(-1)
                )
            elif isinstance(self.criterion, JointCTCCrossEntropyLoss):
                loss, ctc_loss, cross_entropy_loss = self.criterion(
                    encoder_log_probs=encoder_log_probs.transpose(0, 1),
                    decoder_log_probs=outputs.contiguous().view(-1, outputs.size(-1)),
                    output_lengths=encoder_output_lengths,
                    targets=targets,
                    target_lengths=target_lengths
                )
            elif isinstance(self.criterion, nn.CrossEntropyLoss):
                loss = self.criterion(
                    outputs.contiguous().view(-1, outputs.size(-1)), targets.contiguous().view(-1)
                )
            else:
                raise ValueError(f"Unsupported Criterion: {self.criterion}")

        elif self.architecture in ('deepspeech2', 'jasper', 'conformer'):
            outputs, output_lengths = model(inputs, input_lengths)
            loss = self.criterion(outputs.transpose(0, 1), targets, output_lengths, target_lengths)

        else:
            raise ValueError("Unsupported model : {0}".format(self.architecture))

        return outputs, loss, ctc_loss, cross_entropy_loss

    def _save_result(self, target_list: list, predict_list: list) -> None:
        results = {
            'targets': target_list,
            'predictions': predict_list
        }
        date_time = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        save_path = f"{date_time}-valid.csv"
                                
        results = pd.DataFrame(results)
        results.to_csv(save_path, index=False, encoding='cp949')
    
    def __save_epoch_result(self, train_result: list, valid_result: list) -> None:
        """ Save result of epoch """
        train_dict, train_loss, train_cer = train_result
        valid_dict, valid_loss, valid_cer = valid_result

        train_dict["loss"].append(train_loss)
        valid_dict["loss"].append(valid_loss)

        train_dict["cer"].append(train_cer)
        valid_dict["cer"].append(valid_cer)

        train_df = pd.DataFrame(train_dict)
        valid_df = pd.DataFrame(valid_dict)

        train_df.to_csv(SupervisedTrainer.TRAIN_RESULT_PATH, encoding="cp949", index=False)
        valid_df.to_csv(SupervisedTrainer.VALID_RESULT_PATH, encoding="cp949", index=False)

    def __save_step_result(self, train_step_result: dict, loss: float, cer: float) -> None:
        """ Save result of --save_result_every step """
        train_step_result["loss"].append(loss)
        train_step_result["cer"].append(cer)

        train_step_df = pd.DataFrame(train_step_result)
        train_step_df.to_csv(SupervisedTrainer.TRAIN_STEP_RESULT_PATH, encoding="cp949", index=False)
