from arekit.common.experiment.data_type import DataType
from arekit.common.experiment.name_provider import ExperimentNameProvider
from arekit.common.folding.nofold import NoFolding
from arekit.common.labels.base import NoLabel
from arekit.common.labels.provider.constant import ConstantLabelProvider
from arekit.common.labels.scaler.base import BaseLabelScaler
from arekit.common.opinions.annot.algo.pair_based import PairBasedOpinionAnnotationAlgorithm
from arekit.common.opinions.annot.base import BaseOpinionAnnotator
from arekit.common.pipeline.base import BasePipeline
from arekit.contrib.networks.core.predict.tsv_writer import TsvPredictWriter
from arekit.contrib.utils.processing.lemmatization.mystem import MystemWrapper

from arelight.demo.utils import read_synonyms_collection
from arelight.pipelines.backend_brat_json import BratBackendContentsPipelineItem
from arelight.pipelines.inference_bert import BertInferencePipelineItem
from arelight.pipelines.serialize_bert import BertTextsSerializationPipelineItem
from arelight.samplers.types import SampleFormattersService
from arelight.text.pipeline_entities_bert_ontonotes import BertOntonotesNERPipelineItem


def demo_infer_texts_bert_pipeline(texts_count,
                                   synonyms_filepath,
                                   output_dir,
                                   bert_config_path,
                                   bert_vocab_path,
                                   bert_finetuned_ckpt_path,
                                   entity_fmt,
                                   labels_scaler,
                                   stemmer=MystemWrapper(),
                                   text_b_type=SampleFormattersService.name_to_type("nli_m"),
                                   terms_per_context=50,
                                   do_lowercase=False,
                                   max_seq_length=128):
    assert(isinstance(texts_count, int))
    assert(isinstance(output_dir, str))
    assert(isinstance(synonyms_filepath, str))
    assert(isinstance(labels_scaler, BaseLabelScaler))

    PairBasedOpinionAnnotationAlgorithm(
        dist_in_terms_bound=None,
        label_provider=ConstantLabelProvider(label_instance=NoLabel()))

    opin_annot = BaseOpinionAnnotator()

    ppl = BasePipeline(pipeline=[

        BertTextsSerializationPipelineItem(
            synonyms=read_synonyms_collection(synonyms_filepath=synonyms_filepath, stemmer=stemmer),
            terms_per_context=terms_per_context,
            entities_parser=BertOntonotesNERPipelineItem(
                lambda s_obj: s_obj.ObjectType in ["ORG", "PERSON", "LOC", "GPE"]),
            entity_fmt=entity_fmt,
            name_provider=ExperimentNameProvider(name="example-bert", suffix="infer"),
            text_b_type=text_b_type,
            output_dir=output_dir,
            data_folding=NoFolding(doc_ids_to_fold=list(range(texts_count)),
                                   supported_data_types=[DataType.Test])),

        BertInferencePipelineItem(
            data_type=DataType.Test,
            predict_writer=TsvPredictWriter(),
            bert_config_file=bert_config_path,
            model_checkpoint_path=bert_finetuned_ckpt_path,
            vocab_filepath=bert_vocab_path,
            max_seq_length=max_seq_length,
            do_lowercase=do_lowercase,
            labels_scaler=labels_scaler),

        BratBackendContentsPipelineItem(label_to_rel={
            str(labels_scaler.label_to_uint(ExperimentPositiveLabel())): "POS",
            str(labels_scaler.label_to_uint(ExperimentNegativeLabel())): "NEG"
        },
            obj_color_types={"ORG": '#7fa2ff', "GPE": "#7fa200", "PERSON": "#7f00ff", "Frame": "#00a2ff"},
            rel_color_types={"POS": "GREEN", "NEG": "RED"},
        )
    ])

    return ppl
