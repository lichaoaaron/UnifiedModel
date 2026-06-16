parser grammar SplMModelParser;

options {
    tokenVocab=SplBaseLexer;
}

mModelEntry
    : mModelSource EOF
    ;

mModelSource
    : SEARCH_SPL_ENTITY withParams?
    | SEARCH_SPL_TOPO withParams?
    | SEARCH_SPL_MMODEL withParams?
    ;

withParams
    : SEARCH_SPL_WITH SEARCH_LPAREN withParamKey SEARCH_EQ withParamValue (SEARCH_COMMA withParamKey SEARCH_EQ withParamValue)* SEARCH_RPAREN
    ;

withParamKey
    : SEARCH_IDENTIFY
    | SEARCH_DOUBLE_STRING
    ;

withParamValue
    : withParamSingleValue
    | withParamMultiValue
    | withParamTupleList
    ;

withParamMultiValue
    : SEARCH_LBRACK withParamSingleValue (SEARCH_COMMA withParamSingleValue)* SEARCH_RBRACK
    ;

withParamTupleList
    : SEARCH_LBRACK withParamTuple (SEARCH_COMMA withParamTuple)* SEARCH_RBRACK
    ;

withParamTuple
    : SEARCH_LPAREN SEARCH_SINGLE_STRING SEARCH_COMMA SEARCH_SINGLE_STRING SEARCH_RPAREN
    ;

withParamSingleValue
    : SEARCH_SINGLE_STRING
    | SEARCH_LONG
    | SEARCH_FLOAT
    | SEARCH_SPL_TRUE
    | SEARCH_SPL_FALSE
    | SEARCH_BACK_QUOTA_STRING
    | SEARCH_SPL_IDENTIFY_REF
    ;
