import React, { useState } from 'react';

import {useQuery} from "@apollo/client";
import {connect } from 'react-redux'
import TotalValue from './TotalValue'
import BlocksVsCreated from './chart/BlocksVsCreated'
import Pie from './chart/Pie'
import {COUNT_BLOCKTYPE} from '../graphql'
import {ALL_BLOCK} from '../graphql'



function BlockComponent(props) {
const [height, setHeight] = useState(300);

const { loading, error,  data:allBlock } = useQuery(ALL_BLOCK);
const { loadingCountBlock, errorCountBlock,  data: countBlockType } = useQuery(COUNT_BLOCKTYPE);



if (loading) return <p>Loading...</p>;
if (error) return <p>Errore nel caricare la pagina  :</p>;
if (loadingCountBlock) return <p>Loading...</p>;
if (errorCountBlock) return <p>Errore nel caricare la pagina  :</p>;

props.loadAllBlock(allBlock);
props.loadCountBlockType(countBlockType);
  
  let width = 800

  return (
    <div>
    <TotalValue countBlockType = {countBlockType}  />

     <div className="row " > 
        <div className="col-lg-4 " >
            <Pie data = {countBlockType.countBlockType}   />
          </div>
          <div className="col-lg-6 " >
          <BlocksVsCreated data = {allBlock} height = {height} width = {width}  /> 
          </div>
        </div>
       <br></br>


</div>
  );
  
}


const mapState = (state) => ({
  count: state.dashboard.count,
  allBlock: state.dashboard.allBlock,
  countBlockType : state.dashboard.countBlockType,
  
})

const mapDispatch = (dispatch, payload) => ({
  increment: (payload) => dispatch.dashboard.increment(payload),
  incrementAsync: () => dispatch.dashboard.incrementAsync(payload),
  loadAllBlock: (payload) => dispatch.dashboard.loadAllBlock(payload),
  loadCountBlockType: (payload) => dispatch.dashboard.loadCountBlockType(payload),
})


export default connect(mapState, mapDispatch)(BlockComponent)


