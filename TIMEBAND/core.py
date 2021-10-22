from utils.logger import Logger
from utils.device import init_device

from torch.utils.data import DataLoader
from TIMEBAND.loss import TIMEBANDLoss
from TIMEBAND.model import TIMEBANDModel
from TIMEBAND.metric import TIMEBANDMetric
from TIMEBAND.dataset import TIMEBANDDataset
from TIMEBAND.trainer import TIMEBANDTrainer
from TIMEBAND.runner import TIMEBANDRunner
from TIMEBAND.dashboard import TIMEBANDDashboard

logger = Logger(__file__)


class TIMEBANDCore:
    """
    TIMEBANDBand : Timeseries Analysis using GAN Band

    The Model for Detecting anomalies / Imputating missing value in timeseries data

    """

    def __init__(self, config: dict) -> None:
        # Set device
        self.device = init_device()

        # Set Config
        self.set_config(config=config)

        # Dataset & Model Settings
        self.dataset = TIMEBANDDataset(self.dataset_cfg, self.device)
        self.models = TIMEBANDModel(self.models_cfg, self.device)

        # Losses and Metric Settings
        self.metric = TIMEBANDMetric(self.device)
        self.losses = TIMEBANDLoss(self.losses_cfg, self.device)

        # Visualize Settings
        self.dashboard = TIMEBANDDashboard(self.dashboard_cfg, self.dataset)

    def init_dataset(self):
        self.dataset = TIMEBANDDataset(self.dataset_cfg, self.device)

    def set_config(self, config: dict) -> None:
        """
        Setting configuration

        If config/config.json is not exists,
        Use default config 'config.yml'
        """
        logger.info("  Config : config settings")

        core = config["core"]

        # Core configs
        self.mode = core["mode"]
        self.pretrain = core["pretrain"]

        self.workers = core["workers"]
        self.batch_size = core["batch_size"]
        self.seed = core["seed"]

        # Configuration Categories
        self.dataset_cfg = config["dataset"]
        self.models_cfg = config["models"]
        self.losses_cfg = config["losses"]
        self.trainer_cfg = config["trainer"]
        self.dashboard_cfg = config["dashboard"]

    def train(self) -> None:
        self.models.initiate(dims=self.dataset.dims)

        self.trainer = TIMEBANDTrainer(
            self.trainer_cfg,
            self.dataset,
            self.models,
            self.metric,
            self.losses,
            self.dashboard,
            self.device,
        )

        for k in range(self.dataset.window_sliding + 1):
            logger.info(f"Run ({k + 1}/{self.dataset.window_sliding + 1})")

            if self.pretrain:
                self.models.load("BEST")

            # Dataset
            trainset, validset = self.dataset.load_dataset(k + 1)
            trainset = self.loader(trainset)
            validset = self.loader(validset)

            # Model
            self.trainer.train(trainset, validset)

            logger.info(f"Done ({k + 1}/{self.dataset.window_sliding + 1}) ")

    def run(self, netG=None):
        self.runner = TIMEBANDRunner(
            self.trainer_cfg,
            self.dataset,
            self.models,
            self.metric,
            self.dashboard,
            self.device,
        )

        trainset, validset = self.dataset.load_dataset(0)
        trainset = self.loader(trainset)
        validset = self.loader(validset)

        output = self.runner.inference(trainset, validset)
        output.to_csv(f"./outputs/output.csv", index=False)

    def visualize(self):
        pass

    def loader(self, dataset: TIMEBANDDataset):
        dataloader = DataLoader(dataset, self.batch_size, num_workers=self.workers)
        return dataloader

    def clear(self):
        del self.dataset
        self.dataset = None
