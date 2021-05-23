import React, { useState,useEffect } from 'react';
import { connect  } from 'react-redux'

import {useQuery} from "@apollo/client";
import TotalCategories from './TotalCategories'
import CategoryList from './CategoryList'
import CategorySelect from './CategorySelect'
import {ALL_CATEGORY} from '../graphql'

import Bar from './chart/Bar'
import { NoSchemaIntrospectionCustomRule } from 'graphql';




function Category(props) {

const [showSon, setShowSon] = useState(true)

// const [categorySelected, setCategorySelected] = useState(props.categorySelected)

  
useEffect(() => {
//  props.setSons(sons)
    document.title = `Categories`;
  return () => {
  }

   } , [props.categorySelected,props.sons] );

 
  const { loading, error,  data:allCategory } = useQuery(ALL_CATEGORY);
  if (loading) return <p>Loading...</p>;
  if (error) return <p>Errore nel caricare la pagina  :</p>;
   
   // function GetLevelZero(obj) {
   //    return (obj.level === 0)
   //  }
   //  var categoryLevelZero = allCategory.allCategory.filter(GetLevelZero);
   


    function getSons(obj) {
 //     return (categoryLevelZero[0].label == obj.parent) 
 alert("aaa")
      return (props.categorySelected === obj.parent) 
     }
    
     function showSons() {
       alert("showsons")
        setShowSon(!showSon)
     }

    var sons = allCategory.allCategory.filter(getSons);
    alert("sons")
    props.setSons(sons)
    var title = "Component by Category: " + props.categorySelected
    // props.setSons(sons)
      
  //  <TotalCategories allCategory = {allCategory.allCategory}  categoryLevelZero = {props.categorySelected} sons = {sons} />
    return (
      <div className = "ml-2">
       <CategorySelect allCategory = {allCategory.allCategory}   />
 
    <div  className="row" > 
      <div className="col-lg-5 "> 
      <h4   onClick = {showSons} > {props.categorySelected}  {sons.allSonsCount} </h4>
        { showSon ?  <CategoryList  sons = {sons} allCategory = {allCategory}  /> : null }
      </div>
   
      <div className="col-lg-5 "> 
         { showSon ?  <Bar  sons = {sons} height = {800} title = {title}  /> : null }
    
     </div>


    <br></br>
  
</div>
</div>
  );
  
}

const mapState = (state) => ({
  categorySelected: state.dashboard.categorySelected,
  sons :state.dashboard.sons  
})

const mapDispatch = (dispatch, payload) => ({
  setCategorySelected: (payload) => dispatch.dashboard.setCategorySelected(payload),
  setSons: (payload) => dispatch.dashboard.setSons(payload),

})


export default connect(mapState, mapDispatch)(Category)