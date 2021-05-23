import { printIntrospectionSchema } from 'graphql';
import {connect } from 'react-redux'




export default function BlockManageSearchBar(props) {

  const searchText = props.searchText

  function handleTestoRicercaChange(e) {
    props.setSearchText(e.target.value);
    props.setLimit(2000)
  }
  
  
  return (
    <form>
      <input
      type="text"
      placeholder="Search..."
      value={searchText}
      onChange={handleTestoRicercaChange}
      />
  
    </form>
  );
  
}


