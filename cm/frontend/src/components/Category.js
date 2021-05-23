import React, { useState,useEffect } from 'react';
import { connect  } from 'react-redux'

import {useQuery} from "@apollo/client";
import CategoryList from './CategoryList'
import CategorySelect from './CategorySelect'
import {ALL_CATEGORY} from '../graphql'



import Bar from './chart/Bar'



function Category(props) {

const [showSon, setShowSon] = useState(true)

useEffect(() => {
  document.title = `Categories`;
//  props.setSons(sons)
  return () => {
  }
  
} , [props.categorySelected] );

//   LOAD ALL CATEGORY FROM DATABASE WITH REFETCH
const { loading, error,  data:allCategory, refetch,networkStatus } = useQuery(ALL_CATEGORY,
          {notifyOnNetworkStatusChange: true,}
          );
if (networkStatus === networkStatus.refetch) return <p>Refetching  :</p>;
if (loading) return <p>Loading...</p>;
if (error) return <p>Errore nel caricare la pagina  :</p>;
var categories = allCategory.allCategory.concat([])
 

    function getSons(obj) {
      return (props.categorySelected === obj.parent || props.categorySelected === obj.label) 
     }
    
     


     function showSons(e) {
       alert("Click")
        if (props.categorySelected !== "") {
          alert("aa")
          setShowSon(true)
          props.setCategorySelected("")
          return
        }
        
          if (e.target.id === props.categorySelected) {
        }
        else {
          setShowSon(!showSon)
        }
     }

     var sons = categories.filter(getSons);
     var sonsWithParent = JSON.parse(JSON.stringify(sons ));

      var totalSons = 0
      var index = 0
      for (let i = 0; i < sonsWithParent.length; i++) {
          if (sonsWithParent[i].label === props.categorySelected) {
            index = i
            continue
          }
          totalSons = totalSons + sons[i].allBlockCount 
      }

    sonsWithParent[index].allBlockCount = sonsWithParent[index].allBlockCount - totalSons

  var title = "Component by Category: " + props.categorySelected
  var legend = {
      titleAsseX : "Component",
      titleAsseY : "Components' Number",
      labelTextColor: "#ffffff"

    }

    // <button onClick={() => refetch()}>Refetch!</button>
      
    return (
      <div className = "ml-2">
       <CategorySelect allCategory = {allCategory.allCategory} refetch = {refetch}  />
      <div  className="row" > 
            <div className="col-lg-5 "> 
            <h4   onClick = {e => showSons(e)} id = "Part"> {props.categorySelected}  {sons.allBlockCount}       </h4>
               { showSon ?  <CategoryList  sons = {sonsWithParent} allCategory = {allCategory}  /> : null }
            </div>

            <div className="col-lg-7 "> 
              { props.subCategorySelected=== "" ?  <Bar  sons = {sonsWithParent} height = {600} title = {title} legend = {legend}  /> : null }
          </div>

    <br></br>

  
</div>
</div>
  );
  
}

const mapState = (state) => ({
  categorySelected: state.dashboard.categorySelected,
  historyCategorySelected: state.dashboard.historyCategorySelected,
  subCategorySelected:state.dashboard.subCategorySelected,
  sons :state.dashboard.sons  
})

const mapDispatch = (dispatch, payload) => ({
  setCategorySelected: (payload) => dispatch.dashboard.setCategorySelected(payload),
  setSons: (payload) => dispatch.dashboard.setSons(payload),
  setHistoryCategorySelected: (payload) => dispatch.dashboard.setHistoryCategorySelected(payload),

})


export default connect(mapState, mapDispatch)(Category)