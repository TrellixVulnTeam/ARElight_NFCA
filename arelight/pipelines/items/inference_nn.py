from os.path import join, dirname

from arekit.common.data.input.readers.tsv import TsvReader
from arekit.common.data.row_ids.multiple import MultipleIDProvider
from arekit.common.data.views.samples import LinkedSamplesStorageView
from arekit.common.experiment.data_type import DataType
from arekit.common.pipeline.context import PipelineContext
from arekit.common.pipeline.items.base import BasePipelineItem
from arekit.contrib.networks.core.callback.writer import PredictResultWriterCallback
from arekit.contrib.networks.core.ctx_inference import InferenceContext
from arekit.contrib.networks.core.model import BaseTensorflowModel
from arekit.contrib.networks.core.model_ctx import TensorflowModelContext
from arekit.contrib.networks.core.pipeline.item_fit import MinibatchFittingPipelineItem
from arekit.contrib.networks.core.pipeline.item_keep_hidden import MinibatchHiddenFetcherPipelineItem
from arekit.contrib.networks.core.pipeline.item_predict import EpochLabelsPredictorPipelineItem
from arekit.contrib.networks.core.pipeline.item_predict_labeling import EpochLabelsCollectorPipelineItem
from arekit.contrib.networks.core.predict.base_writer import BasePredictWriter
from arekit.contrib.networks.factory import create_network_and_network_config_funcs
from arekit.contrib.networks.shapes import NetworkInputShapes
from arekit.contrib.utils.io_utils.samples import SamplesIO
from arekit.contrib.utils.processing.languages.ru.pos_service import PartOfSpeechTypesService


class TensorflowNetworkInferencePipelineItem(BasePipelineItem):

    def __init__(self, model_name, bags_collection_type, model_input_type, predict_writer, samples_io,
                 data_type, bag_size, bags_per_minibatch, nn_io, labels_scaler, callbacks, emb_io):
        assert(isinstance(callbacks, list))
        assert(isinstance(bag_size, int))
        assert(isinstance(predict_writer, BasePredictWriter))
        assert(isinstance(data_type, DataType))
        assert(isinstance(samples_io, SamplesIO))

        # Create network an configuration.
        network_func, config_func = create_network_and_network_config_funcs(
            model_name=model_name, model_input_type=model_input_type)

        # setup network and config parameters.
        self.__network = network_func()
        self.__config = config_func()
        self.__config.modify_classes_count(labels_scaler.LabelsCount)
        self.__config.modify_bag_size(bag_size)
        self.__config.modify_bags_per_minibatch(bags_per_minibatch)
        self.__config.set_class_weights([1, 1, 1])
        self.__config.set_pos_count(PartOfSpeechTypesService.get_mystem_pos_count())
        self.__config.reinit_config_dependent_parameters()

        # intialize model context.
        self.__create_model_ctx = lambda inference_ctx: TensorflowModelContext(
            nn_io=nn_io,
            network=self.__network,
            config=self.__config,
            inference_ctx=inference_ctx,
            bags_collection_type=bags_collection_type)

        self.__callbacks = callbacks + [
            PredictResultWriterCallback(labels_scaler=labels_scaler, writer=predict_writer)
        ]

        self.__writer = predict_writer
        self.__bags_collection_type = bags_collection_type
        self.__data_type = data_type
        self.__samples_io = samples_io
        self.__emb_io = emb_io

    def apply_core(self, input_data, pipeline_ctx):
        assert(isinstance(pipeline_ctx, PipelineContext))

        # Fetch other required in furter information from input_data.
        samples_filepath = self.__samples_io.create_target(
            data_type=self.__data_type,
            data_folding=pipeline_ctx.provide("data_folding"))

        # Setup predicted result writer.
        tgt = pipeline_ctx.provide_or_none("predict_fp")
        if tgt is None:
            tgt = join(dirname(samples_filepath), "predict.tsv.gz")

        # Update for further pipeline items.
        pipeline_ctx.update("predict_fp", tgt)

        data_folding = pipeline_ctx.provide("data_folding")

        # Fetch other required in further information from input_data.
        samples_filepath = self.__samples_io.create_target(self.__data_type, data_folding=data_folding)
        embedding = self.__emb_io.load_embedding(data_folding)
        vocab = self.__emb_io.load_vocab(data_folding)

        # Setup config parameters.
        self.__config.set_term_embedding(embedding)

        inference_ctx = InferenceContext.create_empty()
        inference_ctx.initialize(
            dtypes=[self.__data_type],
            bags_collection_type=self.__bags_collection_type,
            samples_view=LinkedSamplesStorageView(row_ids_provider=MultipleIDProvider()),
            load_target_func=lambda _: samples_filepath,
            samples_reader=TsvReader(),
            has_model_predefined_state=True,
            vocab=vocab,
            labels_count=self.__config.ClassesCount,
            input_shapes=NetworkInputShapes(iter_pairs=[
                (NetworkInputShapes.FRAMES_PER_CONTEXT, self.__config.FramesPerContext),
                (NetworkInputShapes.TERMS_PER_CONTEXT, self.__config.TermsPerContext),
                (NetworkInputShapes.SYNONYMS_PER_CONTEXT, self.__config.SynonymsPerContext),
            ]),
            bag_size=self.__config.BagSize)

        # Model preparation.
        model = BaseTensorflowModel(
            context=self.__create_model_ctx(inference_ctx),
            callbacks=self.__callbacks,
            predict_pipeline=[
                EpochLabelsPredictorPipelineItem(),
                EpochLabelsCollectorPipelineItem(),
                MinibatchHiddenFetcherPipelineItem()
            ],
            fit_pipeline=[MinibatchFittingPipelineItem()])

        self.__writer.set_target(tgt)

        model.predict(do_compile=True)

        return self.__samples_io
