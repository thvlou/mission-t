import * as THREE from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// Export the actual runtime scenery, including all instanced trees, as a portable visual GLB.
// Collision/progress/routes remain in the JSON course asset and are not inferred from this mesh.
export async function exportTrackGLB(scenery) {
 const clone=scenery.clone(true),instances=[];
 clone.traverse(o=>{if(o.isInstancedMesh)instances.push(o);});
 for(const object of instances){
  const parts=[],matrix=new THREE.Matrix4();
  for(let i=0;i<object.count;i++){object.getMatrixAt(i,matrix);parts.push(object.geometry.clone().applyMatrix4(matrix));}
  const geo=mergeGeometries(parts,false);parts.forEach(p=>p.dispose());
  const mesh=new THREE.Mesh(geo,object.material);mesh.name=object.name||'Track vegetation';mesh.position.copy(object.position);mesh.quaternion.copy(object.quaternion);mesh.scale.copy(object.scale);
  object.parent.add(mesh);object.removeFromParent();
 }
 try{return await new GLTFExporter().parseAsync(clone,{binary:true,onlyVisible:true});}
 finally{clone.traverse(o=>{if(o.isMesh&&o.name==='Track vegetation')o.geometry.dispose();});}
}
