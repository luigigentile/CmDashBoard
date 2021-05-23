import React, { useState } from 'react';
import { connect  } from 'react-redux'




  function CategoryList(props) {
    
//  var subSons = []
  const [showSon, setShowSon] = useState(false)
  const [parentLabel, setParentLabel] = useState("")
  const [idSelezionato, setIdSelezionato] = useState(0)
  var historyCategorySelected = props.historyCategorySelected 
 

//  set the weight to bold of item selected
    function setWeight(varId) {
      if (varId === idSelezionato) {
        return ("bold")
      }
      return ("")  
    }

  
    //    MAKE LIST OF SONS
    const sonsList = props.sons.map((x) => {
        return (
       <li style={{fontWeight: setWeight(x.id),} }   name= {x.allSonsCount} id = {x.label} key = {x.id}   onClick = {(e) => showSons(e,x.id)} > {x.label} {x.allBlockCount} </li> 
        )}
    );
    
    function getSons(obj) {
        return ( parentLabel === obj.parent) 
     }
    
     function showSons(e,varId) {
//      alert(e.target.id)
      historyCategorySelected.push(props.categorySelected)
      props.setHistoryCategorySelected(historyCategorySelected)
      var previosParentLabel = parentLabel 
      setParentLabel(e.target.id)
      setIdSelezionato(varId)
//      props.setSubCategorySelected(e.target.id)
      props.setCategorySelected(e.target.id)

    
      if (!parentLabel === previosParentLabel || parentLabel === "") {
        setShowSon(!showSon)
       }

      }
         
        
//    subSons = props.allCategory.allCategory.filter(getSons);
//     var title = "Component by Category: " + parentLabel

//     var legend = {
//       titleAsseX : "Component",
//       titleAsseY : "Components' Number",
//       labelTextColor: "#ffffff"
//     }
    
//    {subSons.length>0 ?    <Bar   sons = {subSons} height = {600} title = {title} legend = {legend} /> : null }
// <Bar   sons = {subSons} height = {600} title = {title} legend = {legend} /> 
// <CategoryList sons = {subSons} parentLabel = {parentLabel} allCategory = {props.allCategory}  /> 

    return (
      <div className="row " > 
        <div className="col-lg-8 ml-n2" >
          {sonsList}
        </div>
        { showSon ?
            <div className="col-lg-8 " >
          </div>
        : null }
        
          <div className="col-lg-4 " >
          { showSon  ?
          <div classname = "row mt-4">
          <br></br>
          <br></br>
          <br></br>
          </div>
             : null }
      </div>
      </div>

  );
  
}


const mapState = (state) => ({
  categorySelected: state.dashboard.categorySelected,
  subCategorySelected:state.dashboard.subCategorySelected,
  historyCategorySelected: state.dashboard.historyCategorySelected,

})

const mapDispatch = (dispatch, payload) => ({
  setCategorySelected: (payload) => dispatch.dashboard.setCategorySelected(payload),
  setSubCategorySelected: (payload) => dispatch.dashboard.setSubCategorySelected(payload),
  setHistoryCategorySelected: (payload) => dispatch.dashboard.setHistoryCategorySelected(payload),

})


export default connect(mapState, mapDispatch)(CategoryList)
