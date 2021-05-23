import React from 'react'
import {connect } from 'react-redux'

function TotalValue({countBlockType,props}) {
    
  return (
    <div className = "ml-4">
      <h2> Totali </h2>
      <div className="row">
                <div className="col-lg-2 border-bottom ">
     <h4> {countBlockType.countBlockType[0].blockType}</h4>
              </div>
              <div className="col-lg-2 border-bottom ">
     <h4> {countBlockType.countBlockType[1].blockType}</h4>
              </div>
        </div>

        <div className="row">
                <div className="col-lg-2 border-bottom ">
     <h4> {countBlockType.countBlockType[0].count}</h4>
              </div>
              <div className="col-lg-2 border-bottom ">
             <h4> {countBlockType.countBlockType[1].count}</h4>
              </div>
        </div>
    </div>
  );
}



const mapState = (state) => ({
      count: state.dashboard.count,
      allBlock: state.dashboard.allBlock,
      countBlockType :state.dashboard.countBlockType,
      
    })
    
    const mapDispatch = (dispatch, payload) => ({
      increment: (payload) => dispatch.dashboard.increment(payload),
      incrementAsync: () => dispatch.dashboard.incrementAsync(payload),
      loadAllBlock: (payload) => dispatch.dashboard.loadAllBlock(payload),
    })
    
    
    export default connect(mapState, mapDispatch)(TotalValue)