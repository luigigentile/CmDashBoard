import {connect } from 'react-redux'
import arrowLeft from '../staticfiles/arrow-left-square.svg';


 function CategorySelect(props) {
  var historyCategorySelected = props.historyCategorySelected 
  

  //      MAKE CATEGORY LIST      
   const categoriesList = props.allCategory.map((x) => {
   //  if (x.allSonsCount> 1) {
      return <option value = {x.label} key = {x.id}>{x.label}</option>
//     }
  }
    );

    
    function setPartCategory() {
      props.setCategorySelected("Part")
    }

    function setCategorySelectedBack() {
      var previousCategorySelected = historyCategorySelected.pop()
      props.setHistoryCategorySelected(historyCategorySelected)
      props.setCategorySelected(previousCategorySelected)
    }


    
    function onChange(e) {
      const target = e.target;
      const valore =  target.value;
      const proprieta = target.name;
      historyCategorySelected.push(props.categorySelected)
      props.setHistoryCategorySelected(historyCategorySelected)
      console.log(proprieta)
      console.log(valore)
      props.setCategorySelected(valore)
      props.setSubCategorySelected("")
     }
      
     
      return (
     <div className = "row ml-2 border-bottom">
      <div className = "col-2">
           <h3> Select a category  </h3>
     </div>
    
         {/*      SELECT A  CATEGORY         */}                  
         <div className="col-lg-5 mt-2 " > 
          <select name="category"
                className = "border-1"
                id="category"
                value= {props.categorySelected}
                onChange={onChange}
                placeholder="category"
                >
            {categoriesList}  
            </select>
            <button   style={{backgroundColor: "#CCE6FF",  color:"black"  }}
                      onClick = {setPartCategory}
                      className = "ml-3">Part</button>


          <button   style={{backgroundColor: "#CCE6FF",  color:"black"  }}
                      onClick = {setCategorySelectedBack}
                      className = "ml-3">
                      
         <img src={arrowLeft} width="23" height="23" className="icon-delete" alt="logo" /> 
                      
              </button>


        </div>  
         <br></br>
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

export default connect(mapState, mapDispatch)(CategorySelect)

