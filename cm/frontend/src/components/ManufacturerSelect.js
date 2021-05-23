import {connect } from 'react-redux'

 function ManufacturerSelect(props) {


  function onChange(e) {
      const target = e.target;
      const valore =  target.value;
      const proprieta = target.name;
      console.log(proprieta)
      console.log(valore)
      props.setMinManufacturerCount(valore)
     }
     
      return (
     <div className = "row ml-2 ">
      <div className = "col-8">
           <h4> Select Minimum Manufacture Component</h4>
     </div>
            {/*      MIN NUMBER COUNT         */}  
              <h4 >
               Minimum Value:
              <input className = "ml-2"  type="number" value={props.minManufacturerCount} onChange={onChange} min="1" max="10" />
            </h4>
  
    <br></br>
</div>
  );
  
}

const mapState = (state) => ({
  minManufacturerCount: state.dashboard.minManufacturerCount,
})

const mapDispatch = (dispatch, payload) => ({
  setMinManufacturerCount: (payload) => dispatch.dashboard.setMinManufacturerCount(payload),
})

export default connect(mapState, mapDispatch)(ManufacturerSelect)

