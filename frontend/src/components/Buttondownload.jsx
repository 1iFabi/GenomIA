import React from 'react';
import styled from 'styled-components';

const Buttondownload = () => (
  <UnavailableNotice role="status">
    El reporte PDF estará disponible cuando los resultados hayan sido revisados y publicados. No se genera un PDF de demostración.
  </UnavailableNotice>
);

const UnavailableNotice = styled.p`
  max-width: 24rem;
  margin: 0;
  color: #29455b;
  font-size: 0.875rem;
  line-height: 1.5;
`;

export default Buttondownload;
