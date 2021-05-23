import { gql} from "@apollo/client";


export const COUNT_BLOCKTYPE = gql`
 { countBlockType {
    blockType
     count
   }
   }
 `




export const countDescendantAllBlock = gql`
 {
  countDescendantAllBlock {
    blockType
    count
      
  }
}
 `


export const ALL_BLOCK = gql`
 {
  allBlock {
    id
    name
    created
       
  }
}
 `

export const ALL_BLOCK_ORDERBY_NAME = gql`
 {
  allBlock(orderBy: "name") {
    id
    name
    created
       
  }
}
 `


export const ALL_CATEGORY = gql`
  {
    allCategory {
    	id
      label
      level
      parent
      sonsCount
      allSonsCount
      allBlockCount
    }
  }
 `

export const ALL_CATEGORY_ORDERBY_LABEL = gql`
{
  allCategoryOrderbyLabel {
    id
    label
    level
    parent
    sonsCount
    allSonsCount
  }
}
`


export const ALL_MANUFACTURER = gql`
 {
    allManufacturer {
       id
       name
      partCount
    }
  }
 `


export const ALL_INTERFACE_FAMILY = gql`
 {
    allInterfaceFamily {
      id
      label
      interfaceTypeCount
      interfaceType {
        id
        name
      }
       
         
    }
  }
 `



