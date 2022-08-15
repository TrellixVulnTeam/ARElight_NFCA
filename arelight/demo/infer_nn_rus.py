from arekit.common.experiment.data_type import DataType
from arekit.common.experiment.name_provider import ExperimentNameProvider
from arekit.common.folding.nofold import NoFolding
from arekit.common.labels.base import NoLabel
from arekit.common.labels.provider.constant import ConstantLabelProvider
from arekit.common.opinions.annot.algo.pair_based import PairBasedOpinionAnnotationAlgorithm
from arekit.common.opinions.annot.base import BaseOpinionAnnotator
from arekit.common.pipeline.base import BasePipeline
from arekit.contrib.networks.core.callback.stat import TrainingStatProviderCallback
from arekit.contrib.networks.core.callback.train_limiter import TrainingLimiterCallback
from arekit.contrib.networks.core.predict.tsv_writer import TsvPredictWriter
from arekit.contrib.networks.enum_name_types import ModelNames
from arekit.contrib.utils.processing.lemmatization.mystem import MystemWrapper

from arelight.demo.labels.base import PositiveLabel, NegativeLabel
from arelight.demo.labels.scalers import ThreeLabelScaler
from arelight.demo.utils import read_synonyms_collection
from arelight.network.nn.common import create_network_model_io, create_bags_collection_type, create_full_model_name
from arelight.pipelines.backend_brat_json import BratBackendContentsPipelineItem
from arelight.pipelines.inference_nn import TensorflowNetworkInferencePipelineItem
from arelight.pipelines.serialize_nn import NetworkTextsSerializationPipelineItem
from arelight.text.pipeline_entities_bert_ontonotes import BertOntonotesNERPipelineItem


def demo_infer_texts_tensorflow_nn_pipeline(texts_count,
                                            model_name, model_input_type, model_load_dir,
                                            frames_collection,
                                            output_dir,
                                            entity_fmt,
                                            synonyms_filepath,
                                            bags_per_minibatch=2,
                                            exp_name_provider=ExperimentNameProvider(name="example", suffix="infer"),
                                            stemmer=MystemWrapper(),
                                            labels_scaler=ThreeLabelScaler(),
                                            terms_per_context=50):
    assert(isinstance(texts_count, int))
    assert(isinstance(model_name, ModelNames))

    nn_io = create_network_model_io(
        full_model_name=create_full_model_name(model_name=model_name, input_type=model_input_type),
        source_dir=model_load_dir,
        target_dir=model_load_dir,
        model_name_tag=u'')

    PairBasedOpinionAnnotationAlgorithm(
        dist_in_terms_bound=None,
        label_provider=ConstantLabelProvider(label_instance=NoLabel()))

    opin_annot = BaseOpinionAnnotator()

    # Declaring pipeline.
    ppl = BasePipeline(pipeline=[

        NetworkTextsSerializationPipelineItem(
            frames_collection=frames_collection,
            synonyms=read_synonyms_collection(synonyms_filepath=synonyms_filepath, stemmer=stemmer),
            terms_per_context=terms_per_context,
            entities_parser=BertOntonotesNERPipelineItem(
                lambda s_obj: s_obj.ObjectType in ["ORG", "PERSON", "LOC", "GPE"]),
            entity_fmt=entity_fmt,
            stemmer=stemmer,
            name_provider=exp_name_provider,
            output_dir=output_dir,
            data_folding=NoFolding(doc_ids_to_fold=list(range(texts_count)),
                                   supported_data_types=[DataType.Test])),

        TensorflowNetworkInferencePipelineItem(
            nn_io=nn_io,
            model_name=model_name,
            data_type=DataType.Test,
            bag_size=1,
            bags_per_minibatch=bags_per_minibatch,
            bags_collection_type=create_bags_collection_type(model_input_type=model_input_type),
            model_input_type=model_input_type,
            labels_scaler=labels_scaler,
            predict_writer=TsvPredictWriter(),
            callbacks=[
                TrainingLimiterCallback(train_acc_limit=0.99),
                TrainingStatProviderCallback(),
            ]),

        BratBackendContentsPipelineItem(label_to_rel={
            str(labels_scaler.label_to_uint(PositiveLabel())): "POS",
            str(labels_scaler.label_to_uint(NegativeLabel())): "NEG"
        },
            obj_color_types={"ORG": '#7fa2ff', "GPE": "#7fa200", "PERSON": "#7f00ff", "Frame": "#00a2ff"},
            rel_color_types={"POS": "GREEN", "NEG": "RED"},
        ),
    ])

    return ppl
