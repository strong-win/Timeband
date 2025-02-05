import torch
import torch.nn as nn
from torch import tensor

from .utils.initiate import init_device


class TimebandMetric:
    def __init__(self) -> None:
        self.device = init_device()
        self.mse = nn.MSELoss()
        self.esp = 1e-7

    def init_score(self):
        self.nme = 0
        self.nmae = 0
        self.rmse = 0

    def scoring(self, true: tensor, pred: tensor, mask: tensor):
        true = torch.tensor(true.values).to(self.device)
        pred = torch.tensor(pred).to(self.device)
        mask = torch.tensor(mask.values).to(self.device)

        nmae = self.NMAE(true, pred, mask)
        rmse = self.RMSE(true, pred, mask)
        nme = self.NME(true, pred, mask)
        return nmae, rmse, nme

    def NME(self, true: tensor, pred: tensor, mask: tensor):
        true, pred = self._masking(true, pred, mask)
        true, pred = self._ignore_zero(true, pred)

        normalized_error = (true - pred) / (self.esp + true)
        normalized_mean_error = torch.mean(normalized_error).to(self.device)
        nme_score = normalized_mean_error.cpu().detach().numpy()

        self.nme += nme_score
        return nme_score

    def NMAE(self, true: tensor, pred: tensor, mask: tensor):
        true, pred = self._masking(true, pred, mask)
        true, pred = self._ignore_zero(true, pred)

        normalized_error = (true - pred) / (self.esp + true)
        normalized_abs_error = torch.abs(normalized_error).to(self.device)
        normalized_mean_abs_error = torch.mean(normalized_abs_error).to(self.device)
        nmae_score = normalized_mean_abs_error.cpu().detach().numpy()

        self.nmae += nmae_score
        return nmae_score

    def RMSE(self, true: tensor, pred: tensor, mask: tensor):
        true, pred = self._masking(true, pred, mask)

        mean_squared_error = self.mse(true, pred)
        root_mean_squared_error = torch.sqrt(mean_squared_error).to(self.device)
        rmse_score = root_mean_squared_error.cpu().detach().numpy()

        self.rmse += rmse_score
        return rmse_score

    def _masking(self, true: tensor, pred: tensor, mask: tensor):
        target = torch.where(mask == 0)
        true = true[target]
        pred = pred[target]
        return true, pred

    def _ignore_zero(self, true: tensor, pred: tensor):
        target = torch.where(true != 0)
        true = true[target]
        pred = pred[target]
        return true, pred

    def score(self, i: int = 0):
        score = {
            "NME": f"{self.nme  / (i + 1):6.3f}",
            "NMAE": f"{self.nmae / (i + 1):7.5f}",
            "RMSE": f"{self.rmse / (i + 1):6.3f}",
        }
        return score
