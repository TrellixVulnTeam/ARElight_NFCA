import unittest

from ru_sent_tokenize import ru_sent_tokenize
from os.path import dirname, join, realpath

from arekit.common.experiment.data_type import DataType
from arekit.common.folding.nofold import NoFolding
from arekit.common.labels.base import NoLabel
from arekit.common.labels.provider.constant import ConstantLabelProvider
from arekit.common.labels.scaler.single import SingleLabelScaler
from arekit.common.labels.str_fmt import StringLabelsFormatter
from arekit.common.news.base import News
from arekit.common.news.entities_grouping import EntitiesGroupingPipelineItem
from arekit.common.news.sentence import BaseNewsSentence
from arekit.common.opinions.annot.algo.pair_based import PairBasedOpinionAnnotationAlgorithm
from arekit.common.pipeline.base import BasePipeline
from arekit.common.synonyms.grouping import SynonymsCollectionValuesGroupingProviders
from arekit.common.text.parser import BaseTextParser
from arekit.common.opinions.annot.algo_based import AlgorithmBasedOpinionAnnotator
from arekit.common.opinions.collection import OpinionCollection
from arekit.contrib.bert.pipelines.items.serializer import BertExperimentInputSerializerPipelineItem
from arekit.contrib.bert.samplers.nli_m import NliMultipleSampleProvider
from arekit.contrib.bert.terms.mapper import BertDefaultStringTextTermsMapper
from arekit.contrib.utils.pipelines.annot.base import attitude_extraction_default_pipeline
from arekit.contrib.utils.io_utils.samples import SamplesIO
from arekit.contrib.utils.pipelines.items.text.terms_splitter import TermsSplitterParser
from arekit.contrib.utils.processing.lemmatization.mystem import MystemWrapper
from arekit.contrib.utils.synonyms.stemmer_based import StemmerBasedSynonymCollection
from arekit.contrib.utils.entities.formatters.str_simple_sharp_prefixed_fmt import SharpPrefixedEntitiesSimpleFormatter
from arekit.contrib.source.synonyms.utils import iter_synonym_groups

from arelight.exp.doc_ops import InMemoryDocOperations
from arelight.pipelines.utils import input_to_docs
from arelight.text.pipeline_entities_bert_ontonotes import BertOntonotesNERPipelineItem


class EntityFilter(object):

    def __init__(self):
        pass

    def is_ignored(self, entity, e_type):
        raise NotImplementedError()


class BertTestSerialization(unittest.TestCase):
    """ This unit test represent a tutorial on how
        AREkit might be applied towards data preparation for BERT
        model.
    """

    current_dir = dirname(realpath(__file__))
    ORIGIN_DATA_DIR = join(current_dir, "../data")
    TEST_DATA_DIR = join(current_dir, "data")

    @staticmethod
    def input_to_docs(texts):
        docs = []
        for doc_id, contents in enumerate(texts):
            sentences = ru_sent_tokenize(contents)
            sentences = list(map(lambda text: BaseNewsSentence(text), sentences))
            doc = News(doc_id=doc_id, sentences=sentences)
            docs.append(doc)
        return docs

    @staticmethod
    def iter_groups(filepath):
        with open(filepath, 'r', encoding='utf-8') as file:
            for data in iter_synonym_groups(file):
                yield data

    @staticmethod
    def __create_neutral_annot(dist_in_terms_bound, dist_in_sentences=0):
        synonyms = StemmerBasedSynonymCollection(iter_group_values_lists=[],
                                                 stemmer=MystemWrapper(),
                                                 is_read_only=False,
                                                 debug=False)

        annotator = AlgorithmBasedOpinionAnnotator(
            annot_algo=PairBasedOpinionAnnotationAlgorithm(
                dist_in_sents=dist_in_sentences,
                dist_in_terms_bound=dist_in_terms_bound,
                label_provider=ConstantLabelProvider(NoLabel())),
            create_empty_collection_func=lambda: OpinionCollection(
                opinions=[],
                synonyms=synonyms,
                error_on_duplicates=True,
                error_on_synonym_end_missed=False),
            get_doc_existed_opinions_func=lambda _: None)

        return annotator

    def test(self):

        # Declare input texts.
        texts = [
            # Text 1.
            """24 марта президент США Джо Байден провел переговоры с
               лидерами стран Евросоюза в Брюсселе, вызвав внимание рынка и предположения о
               том, что Америке удалось уговорить ЕС совместно бойкотировать российские нефть
               и газ.  Европейский Союз крайне зависим от России в плане поставок нефти и
               газа."""
        ]

        # Declare synonyms collection.
        synonyms_filepath = join(self.ORIGIN_DATA_DIR, "synonyms.txt")

        synonyms = StemmerBasedSynonymCollection(
            iter_group_values_lists=self.iter_groups(synonyms_filepath),
            stemmer=MystemWrapper(),
            is_read_only=False,
            debug=False)

        # Declare text parser.
        text_parser = BaseTextParser(pipeline=[
            TermsSplitterParser(),
            BertOntonotesNERPipelineItem(lambda s_obj: s_obj.ObjectType in ["ORG", "PERSON", "LOC", "GPE"]),
            EntitiesGroupingPipelineItem(lambda value:
                SynonymsCollectionValuesGroupingProviders.provide_existed_or_register_missed_value(
                    synonyms=synonyms, value=value))
        ])

        # Single label scaler.
        single_label_scaler = SingleLabelScaler(NoLabel())

        # Declare folding and experiment context.
        no_folding = NoFolding(doc_ids_to_fold=list(range(len(texts))),
                               supported_data_types=[DataType.Test])

        # Composing labels formatter and experiment preparation.
        labels_fmt = StringLabelsFormatter(stol={"neu": NoLabel})
        doc_ops = InMemoryDocOperations(docs=input_to_docs(texts))
        entity_fmt = SharpPrefixedEntitiesSimpleFormatter()

        rows_provider = NliMultipleSampleProvider(
            label_scaler=single_label_scaler,
            text_b_labels_fmt=labels_fmt,
            text_terms_mapper=BertDefaultStringTextTermsMapper(
                entity_formatter=entity_fmt
            ))

        pipeline = BasePipeline([
            BertExperimentInputSerializerPipelineItem(
                sample_rows_provider=rows_provider,
                samples_io=SamplesIO(target_dir=self.TEST_DATA_DIR),
                save_labels_func=lambda data_type: data_type != DataType.Test,
                balance_func=lambda data_type: data_type == DataType.Train)
        ])

        # Initialize data processing pipeline.
        test_pipeline = attitude_extraction_default_pipeline(
            annotator=self.__create_neutral_annot(dist_in_terms_bound=50, dist_in_sentences=0),
            get_doc_func=lambda doc_id: doc_ops.get_doc(doc_id),
            text_parser=text_parser,
            value_to_group_id_func=lambda value:
                SynonymsCollectionValuesGroupingProviders.provide_existed_or_register_missed_value(
                    synonyms=synonyms, value=value),
            terms_per_context=50,
            entity_index_func=None)

        pipeline.run(input_data=None,
                     params_dict={
                         "data_folding": no_folding,
                         "data_type_pipelines": {DataType.Test: test_pipeline}
                     })


if __name__ == '__main__':
    unittest.main()
