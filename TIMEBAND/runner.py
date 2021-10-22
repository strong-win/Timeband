import torch
import numpy as np
import pandas as pd

from tqdm import tqdm
from torch.optim import RMSprop, Adam
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt

from utils.logger import Logger
from TIMEBAND.model import TIMEBANDModel
from TIMEBAND.metric import TIMEBANDMetric
from TIMEBAND.dataset import TIMEBANDDataset
from TIMEBAND.dashboard import TIMEBANDDashboard

logger = Logger(__file__)


class TIMEBANDRunner:
    def __init__(
        self,
        config: dict,
        dataset: TIMEBANDDataset,
        models: TIMEBANDModel,
        metric: TIMEBANDMetric,
        dashboard: TIMEBANDDashboard,
        device: torch.device,
    ) -> None:
        # Set device
        self.device = device

        self.dataset = dataset
        self.models = models
        self.metric = metric
        self.dashboard = dashboard

        # Set Config
        config = self.set_config(config=config)

        self.data = None
        self.answer = None
        self.future_data = None

    def set_config(self, config: dict = None) -> dict:
        """
        Configure settings related to the data set.

        params:
            config: Trainer configuration dict
                `config['trainer']`
        """

        self.print_cfg = print_cfg = config["print"]

        # Train option
        self.lr_config = config["learning_rate"]
        self.lr = config["learning_rate"]["base"]
        self.lr_gammaG = config["learning_rate"]["gammaG"]
        self.lr_gammaD = config["learning_rate"]["gammaD"]

        self.trainer_config = config["epochs"]
        self.epochs = config["epochs"]["iter"]
        self.base_epochs = config["epochs"]["base"]
        self.iter_epochs = config["epochs"]["iter"]
        self.iter_critic = config["epochs"]["critic"]

        self.amplifier = config["amplifier"]

        # Print option
        self.print_verbose = print_cfg["verbose"]
        self.print_interval = print_cfg["interval"]

        # Visual option
        self.print_cfg = config["print"]

    def run(self, trainset: DataLoader, validset: DataLoader) -> None:
        logger.info("Train the model")

        # Prediction
        self.data_idx = 0
        self.pred_initate()

        # Dashboard
        self.dashboard.init_figure()

        # Train Section
        self.step(trainset)
        self.step(validset)

        # Dashboard
        self.dashboard.clear_figure()

        self.models.load("BEST")
        self.models.save(best=True)
        
    def pred_initate(self):
        decoded_shape = self.dataset.decode_shape
        (batch_size, forecast_len, target_dims) = decoded_shape

        init_shape3 = (forecast_len - 1, forecast_len, target_dims)
        init_shape2 = (forecast_len - 1, target_dims)

        # version v2.2
        self.pred_data = np.empty(init_shape3)
        self.pred_data[:] = np.nan

        self.preds = np.empty(init_shape2)
        self.preds[:] = np.nan

        self.stds = np.zeros(init_shape2)

    def predicts(self, pred):
        (batch_size, forecast_len, target_dims) = pred.shape
        pred = pred.detach().numpy()

        nan_shape3 = np.empty((batch_size, forecast_len, target_dims))
        nan_shape3[:] = np.nan
        nan_shape2 = np.empty((batch_size, target_dims))
        nan_shape2[:] = np.nan

        self.pred_data = np.concatenate(
            [self.pred_data[1 - forecast_len :], nan_shape3]
        )
        for f in range(forecast_len):
            self.pred_data[f : batch_size + f, f] = pred[:, f]

        self.preds = np.nanmedian(self.pred_data, axis=1)
        self.stds = np.nanstd(self.pred_data, axis=1)

        for f in range(forecast_len - 1, 0, -1):
            gamma = (forecast_len - f) / (forecast_len - 1)
            self.stds[-f] += self.stds[-f - 1] * gamma

        for f in range(1, forecast_len):
            self.stds[f] += self.stds[f - 1] * 0.1
                    
    def inference(self, netG, dataset):
        logger.info("Predict the data")

        # Models Setting
        models = self.models
        self.netD, self.netG = models.init(self.dataset.dims)

        pred_tqdm = tqdm(dataset)
        output = self.inference_step(pred_tqdm)

        return output
        # self.data = None
        # self.answer = None
        # for i, data in enumerate(pred_tqdm):
        #     true_x = data["encoded"].to(self.device)
        #     fake_y = generate(true_x)

        #     pred = self.dataset.denormalize(fake_y.cpu())
        #     # for f in range(self.dataset.decode_dims):
        #     #     pred[:, :, f] = pred[:, :, f] * self.data_gamma[f]

        #     self.eval(pred)
        #     # self.predict(pred_y)

        #     batch_size = pred.shape[0]
        #     future_size = pred.shape[1]
        #     feature_dim = pred.shape[2]
        #     pred = pred.reshape((-1, future_size, feature_dim))
        #     preds = np.concatenate(
        #         [
        #             self.future_data[-batch_size - future_size :].detach().numpy(),
        #             np.zeros((batch_size, future_size, feature_dim)),
        #         ]
        #     )

        #     if self.answer is None:
        #         self.answer = np.zeros(
        #             (batch_size + future_size - 1, future_size, feature_dim)
        #         )
        #         self.index = 0
        #     else:
        #         self.answer = np.concatenate(
        #             [self.answer, np.zeros((batch_size, future_size, feature_dim))],
        #         )

        #     for f in range(future_size):
        #         self.answer[self.index + f : self.index + f + batch_size, f] = preds[
        #             batch_size : 2 * batch_size, f
        #         ]
        #     self.index += batch_size

        # answer = self.answer.reshape(-1, future_size)
        # answer[answer == 0] = np.nan
        # mean_value = np.nanmean(answer, axis=1).reshape((-1, 1))

        # times = pd.DataFrame(self.dataset.preds_times.reshape(-1, 1))
        # output = pd.DataFrame(mean_value)
        # mean_output = pd.concat([times, output], axis=1)

        # return mean_output, output

    def inference_step(self, pred_tqdm: tqdm):
        def discriminate(x):
            return self.netD(x).to(self.device)

        def generate(x):
            return self.netG(x).to(self.device)

        for i, data in enumerate(pred_tqdm):
            true_x = data["encoded"].to(self.device)
            fake_y = generate(true_x)

            pred = self.dataset.denormalize(fake_y.cpu())
            self.eval(pred)

            batch_size = pred.shape[0]
            future_size = pred.shape[1]
            feature_dim = pred.shape[2]
            pred = pred.reshape((-1, future_size, feature_dim))
            preds = np.concatenate(
                [
                    self.future_data[-batch_size - future_size :].detach().numpy(),
                    np.zeros((batch_size, future_size, feature_dim)),
                ]
            )

            if self.answer is None:
                self.answer = np.zeros(
                    (batch_size + future_size - 1, future_size, feature_dim)
                )
                self.index = 0
            else:
                self.answer = np.concatenate(
                    [self.answer, np.zeros((batch_size, future_size, feature_dim))],
                )

            for f in range(future_size):
                self.answer[self.index + f : self.index + f + batch_size, f] = preds[
                    batch_size : 2 * batch_size, f
                ]
            self.index += batch_size

        answer = self.answer.reshape(-1, future_size)
        answer[answer == 0] = np.nan
        mean_value = np.nanmean(answer, axis=1).reshape((-1, 1))

        # times = pd.DataFrame(self.dataset.preds_times.reshape(-1, 1))
        output = pd.DataFrame(mean_value)
        # mean_output = pd.concat([output], axis=1)

        return output

    def eval(self, pred):
        batch_size = pred.shape[0]
        window_size = pred.shape[1]
        future_size = pred.shape[1]
        feature_dim = pred.shape[2]

        pred = pred.reshape((-1, future_size, feature_dim))
        if self.future_data is None:
            empty = torch.empty(pred.shape)
            self.future_data = torch.cat([empty, pred])
            return
        self.future_data = torch.cat([self.future_data, pred])
